"""CNN pralatih (torchvision, bobot ImageNet) yang di-fine-tune untuk kategori AQI.

- Dua tahap: (1) hanya kepala klasifikasi, (2) seluruh jaringan dengan learning rate lebih kecil.
- Augmentasi HANYA geometris (random resized crop skala 0,7-1, flip horizontal). Tanpa jitter warna, kontras,
  blur, atau rotasi: kabut adalah sinyal warna/kontras, dan sudut hitam rotasi mengubah dark channel.
- Loss cross-entropy berbobot kelas. Model terbaik dipilih dengan macro-F1 di validasi (early stopping).
- Ekspor ke ONNX (dipakai API di CPU) dan keluarannya dicocokkan dengan PyTorch.
"""

import logging
import random
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

from airlens.models.preprocess import IMAGE_SIZE, MEAN, STD, load_image, preprocess

logger = logging.getLogger("airlens.models.cnn")

ARCHS = {
    "mobilenet_v3_large": (models.mobilenet_v3_large, models.MobileNet_V3_Large_Weights.IMAGENET1K_V2),
    "efficientnet_b0": (models.efficientnet_b0, models.EfficientNet_B0_Weights.IMAGENET1K_V1),
}


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.backends.cudnn.benchmark = False


def build_model(arch: str, n_classes: int, pretrained: bool = True) -> nn.Module:
    ctor, weights = ARCHS[arch]
    model = ctor(weights=weights if pretrained else None)
    last = model.classifier[-1]
    model.classifier[-1] = nn.Linear(last.in_features, n_classes)
    return model


def head_parameters(model: nn.Module):
    return model.classifier.parameters()


class ImageDataset(Dataset):
    def __init__(self, paths: list[str], labels: list[int], train: bool):
        self.paths, self.labels, self.train = paths, labels, train
        norm = transforms.Normalize(MEAN.tolist(), STD.tolist())
        if train:
            self.tf = transforms.Compose([
                transforms.RandomResizedCrop(IMAGE_SIZE, scale=(0.7, 1.0), ratio=(3 / 4, 4 / 3)),
                transforms.RandomHorizontalFlip(),
                transforms.ToTensor(), norm,
            ])
        else:  # sama dengan preprocess.py: resize utuh tanpa crop
            self.tf = transforms.Compose([transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)), transforms.ToTensor(), norm])

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, i: int):
        return self.tf(load_image(self.paths[i], draft=self.train)), self.labels[i]


def _worker_init(worker_id: int) -> None:
    seed = torch.initial_seed() % 2**32
    np.random.seed(seed)
    random.seed(seed)


def _loader(paths, labels, train: bool, batch_size: int, workers: int, seed: int) -> DataLoader:
    g = torch.Generator()
    g.manual_seed(seed)
    return DataLoader(ImageDataset(paths, labels, train), batch_size=batch_size, shuffle=train, num_workers=workers,
                      worker_init_fn=_worker_init, generator=g, persistent_workers=workers > 0)


@torch.no_grad()
def predict_logits(model: nn.Module, loader: DataLoader, device: str) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    out, ys = [], []
    for x, y in loader:
        out.append(model(x.to(device)).float().cpu().numpy())
        ys.append(np.asarray(y))
    return np.concatenate(out), np.concatenate(ys)


def train_cnn(arch: str, tr_paths, tr_y, val_paths, val_y, n_classes: int, cfg: dict, seed: int, device: str,
              on_epoch=None) -> tuple[nn.Module, dict]:
    """Latih dan kembalikan model dengan macro-F1 validasi terbaik serta riwayat per epoch."""
    seed_everything(seed)
    model = build_model(arch, n_classes).to(device)
    counts = np.bincount(tr_y, minlength=n_classes).astype(float)
    weights = np.where(counts > 0, counts.sum() / (n_classes * np.maximum(counts, 1)), 0.0)
    loss_fn = nn.CrossEntropyLoss(weight=torch.tensor(weights, dtype=torch.float32, device=device))
    train_dl = _loader(tr_paths, tr_y, True, cfg["batch_size"], cfg["num_workers"], seed)
    val_dl = _loader(val_paths, val_y, False, cfg["batch_size"], cfg["num_workers"], seed)

    stages = [("head", cfg["epochs_head"], cfg["lr_head"]), ("full", cfg["epochs_full"], cfg["lr_full"])]
    best = {"macro_f1": -1.0, "state": None, "epoch": -1}
    history, epoch, stale = [], 0, 0
    for stage, n_epochs, lr in stages:
        for p in model.parameters():
            p.requires_grad = stage == "full"
        for p in head_parameters(model):
            p.requires_grad = True
        opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr,
                                weight_decay=cfg["weight_decay"])
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(1, n_epochs))
        for _ in range(n_epochs):
            model.train()
            total, n = 0.0, 0
            for x, y in train_dl:
                x, y = x.to(device), y.to(device)
                opt.zero_grad()
                loss = loss_fn(model(x), y)
                loss.backward()
                opt.step()
                total += loss.item() * len(y)
                n += len(y)
            sched.step()
            logits, ys = predict_logits(model, val_dl, device)
            f1 = f1_score(ys, logits.argmax(1), labels=list(range(n_classes)), average="macro", zero_division=0)
            history.append({"epoch": epoch, "stage": stage, "train_loss": total / max(n, 1), "val_macro_f1": float(f1)})
            logger.info("%s epoch %d (%s): loss %.4f, val macro-F1 %.4f", arch, epoch, stage, total / max(n, 1), f1)
            if on_epoch:
                on_epoch(history[-1])
            if f1 > best["macro_f1"]:
                best = {"macro_f1": float(f1), "state": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
                        "epoch": epoch}
                stale = 0
            else:
                stale += 1
            epoch += 1
            if stage == "full" and stale >= cfg["patience"]:
                break
    model.load_state_dict(best["state"])
    return model.cpu().eval(), {"history": history, "best_epoch": best["epoch"], "best_val_macro_f1": best["macro_f1"]}


def val_logits(model: nn.Module, paths, labels, cfg: dict, seed: int) -> np.ndarray:
    return predict_logits(model, _loader(paths, labels, False, cfg["batch_size"], cfg["num_workers"], seed), "cpu")[0]


class WithEmbedding(nn.Module):
    """Keluaran (logits, embedding). Embedding = fitur hasil pooling sebelum kepala klasifikasi; dipakai monitoring drift."""

    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model

    def forward(self, x):
        emb = torch.flatten(self.model.avgpool(self.model.features(x)), 1)
        return self.model.classifier(emb), emb


def export_onnx(model: nn.Module, out: Path, sample_image: str) -> float:
    """Ekspor ke ONNX (output: logits, embedding), lalu kembalikan selisih maksimum logit ONNX vs PyTorch."""
    import onnxruntime as ort

    model = model.cpu().eval()
    dummy = torch.zeros(1, 3, IMAGE_SIZE, IMAGE_SIZE)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Pembungkus harus eval(): setelah ekspor PyTorch mengembalikan mode pembungkus beserta submodulnya, sehingga
    # pembungkus mode train akan diam-diam memindahkan model asli ke mode train (dropout/BatchNorm aktif).
    torch.onnx.export(WithEmbedding(model).eval(), dummy, str(out), input_names=["image"],
                      output_names=["logits", "embedding"],
                      dynamic_axes={"image": {0: "batch"}, "logits": {0: "batch"}, "embedding": {0: "batch"}},
                      opset_version=17, dynamo=False)
    model.eval()
    x = preprocess(sample_image)
    sess = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    onnx_out = sess.run(["logits"], {"image": x})[0]
    with torch.no_grad():
        torch_out = model(torch.from_numpy(x)).numpy()
    return float(np.abs(onnx_out - torch_out).max())
