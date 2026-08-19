import sys
import requests
from PyQt5.QtWidgets import QWidget, QApplication, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QSlider, QListWidget, QPushButton
from PyQt5.QtCore import Qt


class MyWindow(QWidget) :
    def __init__(self) :
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.joint_value = []

        for i in range (4) :
            self.joint_value.append(90)
    
        main_layout = QHBoxLayout()

        left_layout = self.left_console()
        right_layout = self.right_console()

        main_layout.addLayout(left_layout,2)
        main_layout.addLayout(right_layout,1)

        self.setLayout(main_layout)
        self.setWindowTitle("Robot Arm Slider")

    def left_console(self) :
        slider_layout = QVBoxLayout()

        self.slider = []
        self.value_label = []

        for i in range(4) :
            slider_line = QHBoxLayout()
            slider_line.addWidget(QLabel(f"Joint {i+1} :"))

            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 180)
            slider.setValue(90)
            self.slider.append(slider)
            slider.valueChanged.connect(
                lambda value, idx=i: self.joint_changed(idx, value)
            )
            slider.sliderReleased.connect(
                lambda idx = i : self.move_joint(idx)
            )
            slider_line.addWidget(self.slider[i])

            value_label = QLabel("90°")
            self.value_label.append(value_label)
            slider_line.addWidget(self.value_label[i])
            slider_layout.addLayout(slider_line)
            
        return slider_layout

    def right_console(self) :
        main_layout = QVBoxLayout()
        self.list_widget = QListWidget()
        main_layout.addWidget(self.list_widget)

        button_layout = QHBoxLayout()
        self.add_button = QPushButton("ADD")
        self.remove_button = QPushButton("REMOVE")
        self.add_button.clicked.connect(self.add_item)
        self.remove_button.clicked.connect(self.remove_item)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.remove_button)
        main_layout.addLayout(button_layout)

        self.move_button = QPushButton("MOVE")
        self.home_button = QPushButton("HOME")
        self.move_button.clicked.connect(self.move)
        self.home_button.clicked.connect(self.home)
        main_layout.addWidget(self.move_button)
        main_layout.addWidget(self.home_button)
        return main_layout

    def joint_changed(self, idx, value) :
        self.value_label[idx].setText(f"{value}°")

    def move_joint(self, idx) :
        self.joint_value[idx] = self.slider[idx].value()
        self.motor()

    def add_item(self):
        text = ",".join(map(str, self.joint_value))
        self.list_widget.addItem(text)

    def remove_item(self) :
        current_row = self.list_widget.currentRow()
        if current_row >= 0 :
            item = self.list_widget.takeItem(current_row)

    def move(self):
        if self.list_widget.currentItem() :
            item = self.list_widget.currentItem()
            text = item.text()
            result = list(map(int, text.split(",")))
            self.joint_value = result.copy()

            self.motor()

            for i in range(4):
                self.slider[i].setValue(self.joint_value[i])

    def home(self):
        for i in range(4):
            self.slider[i].setValue(90)
            self.joint_value[i] = 90
        self.motor()

    def motor(self) : #여기서 self.joint_value  값으로 모터 움직임
        try:
            for i in range(4):
                requests.get(
                    "http://192.168.4.1/servo",
                    params={
                        "id": i,
                        "angle": self.joint_value[i]
                    },
                    timeout=1
                )

            response = requests.get(
                "http://192.168.4.1/move",
                timeout=1
            )
            print(response.text)

        except Exception as e:
            print("통신 오류:", e)
        
    
if __name__ == '__main__' :
    app = QApplication(sys.argv)
    window = MyWindow()

    window.show()
    sys.exit(app.exec_())
