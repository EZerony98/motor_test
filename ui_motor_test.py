# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'motor_test.ui'
##
## Created by: Qt User Interface Compiler version 6.10.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMenu, QMenuBar,
    QPushButton, QSizePolicy, QSpacerItem, QStatusBar,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from pyqtgraph import PlotWidget

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(1129, 622)
        self.actionsss = QAction(MainWindow)
        self.actionsss.setObjectName(u"actionsss")
        self.actionsss_2 = QAction(MainWindow)
        self.actionsss_2.setObjectName(u"actionsss_2")
        self.actionsss_3 = QAction(MainWindow)
        self.actionsss_3.setObjectName(u"actionsss_3")
        self.action = QAction(MainWindow)
        self.action.setObjectName(u"action")
        self.actiona = QAction(MainWindow)
        self.actiona.setObjectName(u"actiona")
        self.actiona_2 = QAction(MainWindow)
        self.actiona_2.setObjectName(u"actiona_2")
        self.action_com_config = QAction(MainWindow)
        self.action_com_config.setObjectName(u"action_com_config")
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.gridLayout = QGridLayout(self.centralwidget)
        self.gridLayout.setObjectName(u"gridLayout")
        self.groupBox = QGroupBox(self.centralwidget)
        self.groupBox.setObjectName(u"groupBox")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox.sizePolicy().hasHeightForWidth())
        self.groupBox.setSizePolicy(sizePolicy)
        self.verticalLayout = QVBoxLayout(self.groupBox)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.label = QLabel(self.groupBox)
        self.label.setObjectName(u"label")

        self.verticalLayout.addWidget(self.label)

        self.input_sn = QLineEdit(self.groupBox)
        self.input_sn.setObjectName(u"input_sn")
        font = QFont()
        font.setPointSize(12)
        self.input_sn.setFont(font)

        self.verticalLayout.addWidget(self.input_sn)

        self.label_11 = QLabel(self.groupBox)
        self.label_11.setObjectName(u"label_11")

        self.verticalLayout.addWidget(self.label_11)

        self.combo_model = QComboBox(self.groupBox)
        self.combo_model.addItem("")
        self.combo_model.addItem("")
        self.combo_model.addItem("")
        self.combo_model.setObjectName(u"combo_model")

        self.verticalLayout.addWidget(self.combo_model)

        self.label_2 = QLabel(self.groupBox)
        self.label_2.setObjectName(u"label_2")

        self.verticalLayout.addWidget(self.label_2)

        self.chk_lcr = QCheckBox(self.groupBox)
        self.chk_lcr.setObjectName(u"chk_lcr")
        font1 = QFont()
        font1.setPointSize(17)
        self.chk_lcr.setFont(font1)

        self.verticalLayout.addWidget(self.chk_lcr)

        self.chk_hioki = QCheckBox(self.groupBox)
        self.chk_hioki.setObjectName(u"chk_hioki")
        self.chk_hioki.setFont(font1)

        self.verticalLayout.addWidget(self.chk_hioki)

        self.chk_labjack = QCheckBox(self.groupBox)
        self.chk_labjack.setObjectName(u"chk_labjack")
        self.chk_labjack.setFont(font1)

        self.verticalLayout.addWidget(self.chk_labjack)

        self.chk_auto = QCheckBox(self.groupBox)
        self.chk_auto.setObjectName(u"chk_auto")
        self.chk_auto.setFont(font1)

        self.verticalLayout.addWidget(self.chk_auto)

        self.verticalSpacer = QSpacerItem(20, 195, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout.addItem(self.verticalSpacer)

        self.label_3 = QLabel(self.groupBox)
        self.label_3.setObjectName(u"label_3")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.label_3.sizePolicy().hasHeightForWidth())
        self.label_3.setSizePolicy(sizePolicy1)
        self.label_3.setMinimumSize(QSize(0, 120))
        self.label_3.setMaximumSize(QSize(16777215, 150))
        self.label_3.setPixmap(QPixmap(u"../../Desktop/LOGO.png"))
        self.label_3.setScaledContents(True)
        self.label_3.setAlignment(Qt.AlignmentFlag.AlignBottom|Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft)

        self.verticalLayout.addWidget(self.label_3)


        self.gridLayout.addWidget(self.groupBox, 0, 0, 1, 1)

        self.groupBox_2 = QGroupBox(self.centralwidget)
        self.groupBox_2.setObjectName(u"groupBox_2")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy2.setHorizontalStretch(3)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.groupBox_2.sizePolicy().hasHeightForWidth())
        self.groupBox_2.setSizePolicy(sizePolicy2)
        self.verticalLayout_2 = QVBoxLayout(self.groupBox_2)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.lbl_status = QLabel(self.groupBox_2)
        self.lbl_status.setObjectName(u"lbl_status")
        self.lbl_status.setMinimumSize(QSize(0, 40))
        self.lbl_status.setStyleSheet(u"background-color: gray; color: white; font-size: 48px; border-radius: 10px;")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.horizontalLayout_3.addWidget(self.lbl_status)

        self.groupBox_3 = QGroupBox(self.groupBox_2)
        self.groupBox_3.setObjectName(u"groupBox_3")
        self.groupBox_3.setMinimumSize(QSize(0, 60))
        self.horizontalLayout_2 = QHBoxLayout(self.groupBox_3)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.lbl_stat_lcr = QLabel(self.groupBox_3)
        self.lbl_stat_lcr.setObjectName(u"lbl_stat_lcr")
        self.lbl_stat_lcr.setStyleSheet(u"color: green; font-weight: bold;")

        self.horizontalLayout_2.addWidget(self.lbl_stat_lcr)

        self.lbl_stat_hioki = QLabel(self.groupBox_3)
        self.lbl_stat_hioki.setObjectName(u"lbl_stat_hioki")
        self.lbl_stat_hioki.setStyleSheet(u"color: green; font-weight: bold;")

        self.horizontalLayout_2.addWidget(self.lbl_stat_hioki)

        self.lbl_stat_labjack = QLabel(self.groupBox_3)
        self.lbl_stat_labjack.setObjectName(u"lbl_stat_labjack")
        self.lbl_stat_labjack.setStyleSheet(u"color: green; font-weight: bold;")

        self.horizontalLayout_2.addWidget(self.lbl_stat_labjack)

        self.lbl_stat_plc = QLabel(self.groupBox_3)
        self.lbl_stat_plc.setObjectName(u"lbl_stat_plc")
        self.lbl_stat_plc.setStyleSheet(u"color: green; font-weight: bold;")

        self.horizontalLayout_2.addWidget(self.lbl_stat_plc)


        self.horizontalLayout_3.addWidget(self.groupBox_3)


        self.verticalLayout_2.addLayout(self.horizontalLayout_3)

        self.horizontalLayout_4 = QHBoxLayout()
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.btn_start = QPushButton(self.groupBox_2)
        self.btn_start.setObjectName(u"btn_start")
        self.btn_start.setMinimumSize(QSize(0, 30))
        self.btn_start.setStyleSheet(u"background-color: #4CAF50; color: white; font-size: 20px; font-weight: bold;")

        self.horizontalLayout_4.addWidget(self.btn_start)

        self.btn_save_data = QPushButton(self.groupBox_2)
        self.btn_save_data.setObjectName(u"btn_save_data")
        self.btn_save_data.setMinimumSize(QSize(0, 30))
        self.btn_save_data.setStyleSheet(u"background-color: #2196F3; color: white; font-size: 20px; font-weight: bold;")

        self.horizontalLayout_4.addWidget(self.btn_save_data)

        self.btn_upload_data = QPushButton(self.groupBox_2)
        self.btn_upload_data.setObjectName(u"btn_upload_data")
        self.btn_upload_data.setStyleSheet(u"background-color: #2196F3; color: white; font-size: 20px; font-weight: bold;")

        self.horizontalLayout_4.addWidget(self.btn_upload_data)

        self.btn_stop = QPushButton(self.groupBox_2)
        self.btn_stop.setObjectName(u"btn_stop")
        self.btn_stop.setMinimumSize(QSize(0, 30))
        self.btn_stop.setStyleSheet(u"background-color: red; color: white;")

        self.horizontalLayout_4.addWidget(self.btn_stop)


        self.verticalLayout_2.addLayout(self.horizontalLayout_4)

        self.graph_widget = PlotWidget(self.groupBox_2)
        self.graph_widget.setObjectName(u"graph_widget")
        self.graph_widget.setMinimumSize(QSize(0, 20))
        self.graph_widget.setStyleSheet(u"background-color: black; border: 2px solid gray;")

        self.verticalLayout_2.addWidget(self.graph_widget)

        self.table_data = QTableWidget(self.groupBox_2)
        if (self.table_data.columnCount() < 8):
            self.table_data.setColumnCount(8)
        __qtablewidgetitem = QTableWidgetItem()
        self.table_data.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.table_data.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.table_data.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.table_data.setHorizontalHeaderItem(3, __qtablewidgetitem3)
        __qtablewidgetitem4 = QTableWidgetItem()
        self.table_data.setHorizontalHeaderItem(4, __qtablewidgetitem4)
        __qtablewidgetitem5 = QTableWidgetItem()
        self.table_data.setHorizontalHeaderItem(5, __qtablewidgetitem5)
        __qtablewidgetitem6 = QTableWidgetItem()
        self.table_data.setHorizontalHeaderItem(6, __qtablewidgetitem6)
        __qtablewidgetitem7 = QTableWidgetItem()
        self.table_data.setHorizontalHeaderItem(7, __qtablewidgetitem7)
        self.table_data.setObjectName(u"table_data")

        self.verticalLayout_2.addWidget(self.table_data)

        self.groupBox_4 = QGroupBox(self.groupBox_2)
        self.groupBox_4.setObjectName(u"groupBox_4")
        self.groupBox_4.setMinimumSize(QSize(0, 50))
        self.label_8 = QLabel(self.groupBox_4)
        self.label_8.setObjectName(u"label_8")
        self.label_8.setGeometry(QRect(20, 30, 58, 16))
        self.label_9 = QLabel(self.groupBox_4)
        self.label_9.setObjectName(u"label_9")
        self.label_9.setGeometry(QRect(100, 30, 58, 16))
        self.label_10 = QLabel(self.groupBox_4)
        self.label_10.setObjectName(u"label_10")
        self.label_10.setGeometry(QRect(190, 30, 58, 16))
        self.label_12 = QLabel(self.groupBox_4)
        self.label_12.setObjectName(u"label_12")
        self.label_12.setGeometry(QRect(270, 30, 58, 16))

        self.verticalLayout_2.addWidget(self.groupBox_4)

        self.verticalLayout_2.setStretch(1, 1)
        self.verticalLayout_2.setStretch(2, 4)
        self.verticalLayout_2.setStretch(3, 3)
        self.verticalLayout_2.setStretch(4, 1)

        self.gridLayout.addWidget(self.groupBox_2, 0, 1, 1, 1)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 1129, 24))
        self.menu = QMenu(self.menubar)
        self.menu.setObjectName(u"menu")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.menubar.addAction(self.menu.menuAction())
        self.menu.addAction(self.actionsss)
        self.menu.addSeparator()
        self.menu.addAction(self.actiona)
        self.menu.addSeparator()
        self.menu.addAction(self.actiona_2)
        self.menu.addSeparator()
        self.menu.addSeparator()
        self.menu.addSeparator()
        self.menu.addAction(self.action_com_config)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.actionsss.setText(QCoreApplication.translate("MainWindow", u"\u8fde\u63a5 LCR \u7535\u6865", None))
        self.actionsss_2.setText(QCoreApplication.translate("MainWindow", u"\u8fde\u63a5 \u531d\u95f4\u6d4b\u8bd5\u4eea", None))
        self.actionsss_3.setText(QCoreApplication.translate("MainWindow", u"\u8fde\u63a5 \u793a\u6ce2\u5668", None))
        self.action.setText(QCoreApplication.translate("MainWindow", u"-", None))
        self.actiona.setText(QCoreApplication.translate("MainWindow", u"\u8fde\u63a5 \u531d\u95f4\u6d4b\u8bd5\u4eea", None))
        self.actiona_2.setText(QCoreApplication.translate("MainWindow", u"\u8fde\u63a5 \u793a\u6ce2\u5668", None))
        self.action_com_config.setText(QCoreApplication.translate("MainWindow", u"\u7aef\u53e3\u914d\u7f6e", None))
        self.groupBox.setTitle(QCoreApplication.translate("MainWindow", u"\u6d4b\u8bd5\u53c2\u6570\u8bbe\u5b9a", None))
        self.label.setText(QCoreApplication.translate("MainWindow", u"\u4ea7\u54c1SN\u7801:", None))
        self.input_sn.setPlaceholderText(QCoreApplication.translate("MainWindow", u"\u8bf7\u626b\u63cf\u4e8c\u7ef4\u7801...", None))
        self.label_11.setText(QCoreApplication.translate("MainWindow", u"\u4ea7\u54c1\u578b\u53f7\uff1a", None))
        self.combo_model.setItemText(0, QCoreApplication.translate("MainWindow", u"22MP2", None))
        self.combo_model.setItemText(1, QCoreApplication.translate("MainWindow", u"19xxx", None))
        self.combo_model.setItemText(2, QCoreApplication.translate("MainWindow", u"22MP4", None))

        self.label_2.setText(QCoreApplication.translate("MainWindow", u"\u542f\u7528\u6d4b\u8bd5\u9879\uff1a", None))
        self.chk_lcr.setText(QCoreApplication.translate("MainWindow", u"1. \u7535\u963b\u7535\u611f (\u540c\u60e0\uff09", None))
        self.chk_hioki.setText(QCoreApplication.translate("MainWindow", u"2. \u531d\u95f4\u7edd\u7f18 (Hioki)", None))
        self.chk_labjack.setText(QCoreApplication.translate("MainWindow", u"3. \u53cd\u7535\u52bf\u6ce2\u5f62\uff08Labjack\uff09", None))
        self.chk_auto.setText(QCoreApplication.translate("MainWindow", u"4. \u81ea\u52a8\u6d4b\u8bd5", None))
        self.label_3.setText("")
        self.groupBox_2.setTitle(QCoreApplication.translate("MainWindow", u"\u8fd0\u884c\u76d1\u63a7\u4e0e\u6570\u636e", None))
        self.lbl_status.setText(QCoreApplication.translate("MainWindow", u"READY", None))
        self.groupBox_3.setTitle(QCoreApplication.translate("MainWindow", u"\u786c\u4ef6\u72b6\u6001", None))
        self.lbl_stat_lcr.setText(QCoreApplication.translate("MainWindow", u"\u25cf LCR \u7535\u6865", None))
        self.lbl_stat_hioki.setText(QCoreApplication.translate("MainWindow", u"\u25cf \u531d\u95f4\u4eea", None))
        self.lbl_stat_labjack.setText(QCoreApplication.translate("MainWindow", u"\u25cf \u91c7\u96c6\u5361", None))
        self.lbl_stat_plc.setText(QCoreApplication.translate("MainWindow", u"\u25cf PLC", None))
        self.btn_start.setText(QCoreApplication.translate("MainWindow", u"\u5f00\u59cb\u6d4b\u8bd5", None))
        self.btn_save_data.setText(QCoreApplication.translate("MainWindow", u"\u4fdd\u5b58\u6570\u636e", None))
        self.btn_upload_data.setText(QCoreApplication.translate("MainWindow", u"\u4e0a\u4f20\u6570\u636e", None))
        self.btn_stop.setText(QCoreApplication.translate("MainWindow", u"\u505c\u6b62/\u590d\u4f4d", None))
        ___qtablewidgetitem = self.table_data.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("MainWindow", u"SN\u7801", None));
        ___qtablewidgetitem1 = self.table_data.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("MainWindow", u"\u9759\u6001\u6d4b\u8bd5\n"
"\u7535\u963b\u7535\u611f", None));
        ___qtablewidgetitem2 = self.table_data.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("MainWindow", u"\u9759\u6001\u6d4b\u8bd5\n"
"\u531d\u95f4", None));
        ___qtablewidgetitem3 = self.table_data.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("MainWindow", u"U\u76f8\n"
"Vp/THD/\u8c10\u6ce2", None));
        ___qtablewidgetitem4 = self.table_data.horizontalHeaderItem(4)
        ___qtablewidgetitem4.setText(QCoreApplication.translate("MainWindow", u"V\u76f8\n"
"Vp/THD/\u8c10\u6ce2", None));
        ___qtablewidgetitem5 = self.table_data.horizontalHeaderItem(5)
        ___qtablewidgetitem5.setText(QCoreApplication.translate("MainWindow", u"W\u76f8\n"
"Vp/THD/\u8c10\u6ce2", None));
        ___qtablewidgetitem6 = self.table_data.horizontalHeaderItem(6)
        ___qtablewidgetitem6.setText(QCoreApplication.translate("MainWindow", u"\u76f8\u4f4d\u5dee", None));
        ___qtablewidgetitem7 = self.table_data.horizontalHeaderItem(7)
        ___qtablewidgetitem7.setText(QCoreApplication.translate("MainWindow", u"\u5224\u65ad", None));
        self.groupBox_4.setTitle(QCoreApplication.translate("MainWindow", u"\u7edf\u8ba1", None))
        self.label_8.setText(QCoreApplication.translate("MainWindow", u"\u603b\u6570\uff1a0", None))
        self.label_9.setText(QCoreApplication.translate("MainWindow", u"\u5408\u683c\uff1a0", None))
        self.label_10.setText(QCoreApplication.translate("MainWindow", u"\u4e0d\u826f\uff1a0", None))
        self.label_12.setText(QCoreApplication.translate("MainWindow", u"lab", None))
        self.menu.setTitle(QCoreApplication.translate("MainWindow", u"\u901a\u8baf\u8bbe\u7f6e", None))
    # retranslateUi

