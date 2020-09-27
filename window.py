import io
import sys

import folium
import pandas as pd

from PyQt5 import QtCore, QtGui, QtWidgets, QtWebEngineWidgets


class Window(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.initWindow()

    def initWindow(self):
        self.setWindowTitle(self.tr("MAP PROJECT"))
        self.buttonUI()
        self.showMaximized() 

    def buttonUI(self):
        shortPathButton = QtWidgets.QPushButton(self.tr("Refresh map"))
        shortPathButton.setFixedSize(120, 50)
        

        self.view = QtWebEngineWidgets.QWebEngineView()
        self.view.setContentsMargins(50, 50, 50, 50)

        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        lay = QtWidgets.QHBoxLayout(central_widget)

        button_container = QtWidgets.QWidget()
        vlay = QtWidgets.QVBoxLayout(button_container)
        vlay.setSpacing(20)
        vlay.addStretch()
        vlay.addWidget(shortPathButton)
        
        vlay.addStretch()
        lay.addWidget(button_container)
        lay.addWidget(self.view, stretch=1)
        #read data and show location on map
           
        m = folium.Map(location=[52.227830, 21.001819], zoom_start=13)
        data = io.BytesIO()
        m.save(data, close_file=False)
        self.view.setHtml(data.getvalue().decode())
        
        shortPathButton.clicked.connect(self.refresh)
        
    def refresh(self):
        df = pd.read_csv('logs/location_log.txt', header=None,sep='	')
            
        m = folium.Map(location=[df[7][-1:],df[8][-1:]], zoom_start=13)
        for i,row in df.iterrows():
            folium.CircleMarker((df[7][i],df[8][i]), radius=3, weight=2, color='red', fill_color='red', fill_opacity=.5).add_to(m)
        data = io.BytesIO()
        m.save(data, close_file=False)
        self.view.setHtml(data.getvalue().decode())
        
if __name__ == "__main__":
    App = QtWidgets.QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(App.exec())
    

