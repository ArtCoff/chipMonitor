# main.py
import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
import logging


def setup_logging():
    """配置日志系统 - 控制台+文件双输出"""
    import sys
    import os

    # 创建logs目录
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 设置格式
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)

    # 文件处理器
    from datetime import datetime

    log_filename = f"logs/mqtt_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # 测试输出
    test_msg = "✅ 日志系统初始化完成"
    print(test_msg)
    logging.info(test_msg)
    print(f"📁 日志文件: {log_filename}")

    # 强制刷新
    sys.stdout.flush()


def main():
    setup_logging()
    app = QApplication(sys.argv)
    # app.setStyle("Basic")
    # 创建并显示主窗口
    window = MainWindow()
    window.show()
    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
