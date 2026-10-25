import numpy as np
import pytest
from PIL import Image

torch = pytest.importorskip("torch")

from airlens.models import cnn  # noqa: E402
from airlens.models.preprocess import IMAGE_SIZE, preprocess  # noqa: E402


@pytest.mark.parametrize("arch", list(cnn.ARCHS))
def test_model_output_shape(arch):
    m = cnn.build_model(arch, 5, pretrained=False).eval()
    with torch.no_grad():
        assert m(torch.zeros(2, 3, IMAGE_SIZE, IMAGE_SIZE)).shape == (2, 5)


def test_onnx_export_matches_torch(tmp_path):
    img = tmp_path / "x.jpg"
    Image.fromarray(np.random.default_rng(0).integers(0, 255, (300, 400, 3), dtype=np.uint8)).save(img)
    m = cnn.build_model("mobilenet_v3_large", 5, pretrained=False).eval()
    diff = cnn.export_onnx(m, tmp_path / "m.onnx", str(img))
    assert diff < 1e-4


def test_eval_transform_matches_shared_preprocess(tmp_path):
    # Transformasi evaluasi PyTorch harus sama dengan preprocess() yang dipakai ONNX/API.
    img = tmp_path / "x.jpg"
    Image.fromarray(np.random.default_rng(1).integers(0, 255, (300, 400, 3), dtype=np.uint8)).save(img)
    ds = cnn.ImageDataset([str(img)], [0], train=False)
    a = ds[0][0].numpy()
    b = preprocess(str(img))[0]
    assert np.abs(a - b).max() < 0.05  # beda kecil: antialias resize torchvision vs PIL


def test_onnx_has_embedding_output_matching_head(tmp_path):
    import onnxruntime as ort

    img = tmp_path / "x.jpg"
    Image.fromarray(np.random.default_rng(2).integers(0, 255, (300, 400, 3), dtype=np.uint8)).save(img)
    m = cnn.build_model("mobilenet_v3_large", 5, pretrained=False).eval()
    cnn.export_onnx(m, tmp_path / "m.onnx", str(img))
    sess = ort.InferenceSession(str(tmp_path / "m.onnx"), providers=["CPUExecutionProvider"])
    logits, emb = sess.run(["logits", "embedding"], {"image": preprocess(str(img))})
    assert emb.shape == (1, 960)  # MobileNetV3-Large: 960 kanal setelah pooling
    with torch.no_grad():  # kepala klasifikasi PyTorch atas embedding = logits ONNX
        assert np.abs(m.classifier(torch.from_numpy(emb)).numpy() - logits).max() < 1e-4
