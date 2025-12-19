import sys
from PyQt5 import QtWidgets
from app_window import AppWindow


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = AppWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

