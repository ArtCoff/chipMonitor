# paths.py
from pathlib import Path

# 定义项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# 资源目录
QML_DIR = PROJECT_ROOT / "ui" / "qml"
QSS_DIR = PROJECT_ROOT / "ui" / "qss"
ICON_DIR = PROJECT_ROOT / "ui" / "icons"
# CONFIG_DIR = PROJECT_ROOT / "config"
# DATA_DIR = PROJECT_ROOT / "data"
# TEMPLATE_DIR = PROJECT_ROOT / "templates"
# LOG_DIR = PROJECT_ROOT / "logs"


# 确保目录存在
def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


# ensure_dir(LOG_DIR)
ensure_dir(QML_DIR)
ensure_dir(QSS_DIR)
