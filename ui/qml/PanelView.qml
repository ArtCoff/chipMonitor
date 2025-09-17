import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components" as UI

Item {
    id: root
    anchors.fill: parent
    
    // 颜色主题
    readonly property color primaryColor: "#2196F3"
    readonly property color successColor: "#4CAF50"
    readonly property color warningColor: "#FF9800"
    readonly property color dangerColor: "#F44336"
    readonly property color infoColor: "#9C27B0"

    // ✅ 数据连接
    Connections {
        target: dataProcessor
        ignoreUnknownSignals: true

        function onProcessed_data_updated(data) {
            console.log("📊 Panel received data update:", JSON.stringify(data));
            
            // 更新仪表盘
            if (data.focus_error !== undefined) {
                focusGauge.value = data.focus_error;
            }
            if (data.temperature !== undefined) {
                tempGauge.value = data.temperature;
            }
            if (data.vibration !== undefined) {
                vibrationGauge.value = data.vibration;
            }
            if (data.humidity !== undefined) {
                humidityGauge.value = data.humidity;
            }
            
            // 更新工艺阶段
            if (data.process_stage) {
                stageText.text = data.process_stage;
                stageIndicator.color = (data.process_stage === "Expose") ? dangerColor : successColor;
            }
        }

        function onYield_calculated(yieldValue) {
            console.log("📈 Panel received yield:", yieldValue);
            yieldGauge.value = yieldValue;
        }
    }

    Component.onCompleted: {
        console.log("🚀 PanelView initialized");
    }

    // ==================== 仪表盘布局 ====================
    ScrollView {
        anchors.fill: parent
        anchors.margins: 20
        contentWidth: gaugeGrid.implicitWidth
        contentHeight: gaugeGrid.implicitHeight
        
        GridLayout {
            id: gaugeGrid
            width: Math.max(parent.parent.width - 40, 800)
            columns: 3  // ✅ 面板视图使用3列布局，更紧凑
            columnSpacing: 20
            rowSpacing: 20
            
            // ✅ 1. 良率仪表
            GroupBox {
                title: "实时良率"
                Layout.fillWidth: true
                Layout.preferredWidth: (parent.width - 2 * parent.columnSpacing) / 3
                Layout.preferredHeight: 180
                
                UI.Gauge {
                    id: yieldGauge
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 20, parent.height - 40, 150)
                    height: width
                    title: "良率"
                    unit: "%"
                    minValue: 0
                    maxValue: 100
                    value: 95.0
                    gaugeColor: successColor
                    valueFormat: "0.1f"
                }
            }
            
            // ✅ 2. 温度仪表
            GroupBox {
                title: "温度监控"
                Layout.fillWidth: true
                Layout.preferredWidth: (parent.width - 2 * parent.columnSpacing) / 3
                Layout.preferredHeight: 180
                
                UI.Gauge {
                    id: tempGauge
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 20, parent.height - 40, 150)
                    height: width
                    title: "温度"
                    unit: "°C"
                    minValue: 20
                    maxValue: 25
                    value: 22
                    gaugeColor: primaryColor
                    valueFormat: "0.2f"
                }
            }
            
            // ✅ 3. 对焦误差仪表
            GroupBox {
                title: "对焦误差"
                Layout.fillWidth: true
                Layout.preferredWidth: (parent.width - 2 * parent.columnSpacing) / 3
                Layout.preferredHeight: 180
                
                UI.Gauge {
                    id: focusGauge
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 20, parent.height - 40, 150)
                    height: width
                    title: "对焦误差"
                    unit: "μm"
                    minValue: -0.5
                    maxValue: 0.5
                    value: 0
                    gaugeColor: warningColor
                    valueFormat: "0.3f"
                }
            }
            
            // ✅ 4. 振动仪表
            GroupBox {
                title: "振动监控"
                Layout.fillWidth: true
                Layout.preferredWidth: (parent.width - 2 * parent.columnSpacing) / 3
                Layout.preferredHeight: 180
                
                UI.Gauge {
                    id: vibrationGauge
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 20, parent.height - 40, 150)
                    height: width
                    title: "振动"
                    unit: "g"
                    minValue: 0
                    maxValue: 0.15
                    value: 0.05
                    gaugeColor: warningColor
                    valueFormat: "0.3f"
                }
            }
            
            // ✅ 5. 湿度仪表
            GroupBox {
                title: "湿度监控"
                Layout.fillWidth: true
                Layout.preferredWidth: (parent.width - 2 * parent.columnSpacing) / 3
                Layout.preferredHeight: 180
                
                UI.Gauge {
                    id: humidityGauge
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 20, parent.height - 40, 150)
                    height: width
                    title: "湿度"
                    unit: "%"
                    minValue: 40
                    maxValue: 60
                    value: 50
                    gaugeColor: infoColor
                    valueFormat: "0.1f"
                }
            }
            
            // ✅ 6. 工艺阶段显示
            GroupBox {
                title: "工艺状态"
                Layout.fillWidth: true
                Layout.preferredWidth: (parent.width - 2 * parent.columnSpacing) / 3
                Layout.preferredHeight: 180
                
                Column {
                    anchors.centerIn: parent
                    spacing: 15
                    
                    Row {
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: 15
                        
                        Rectangle {
                            id: stageIndicator
                            width: 32
                            height: 32
                            radius: 16
                            color: successColor
                            
                            Behavior on color {
                                ColorAnimation { duration: 300 }
                            }
                        }
                        
                        Text {
                            id: stageText
                            text: "就绪"
                            font.bold: true
                            font.pointSize: 16
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                    
                    // ✅ 详细状态信息
                    GridLayout {
                        anchors.horizontalCenter: parent.horizontalCenter
                        columns: 2
                        columnSpacing: 15
                        rowSpacing: 8
                        
                        Text {
                            text: "曝光次数:"
                            font.pointSize: 11
                            color: "#666"
                        }
                        Text {
                            id: exposureCountText
                            text: "--"
                            font.pointSize: 11
                            font.bold: true
                            color: "#333"
                        }
                        
                        Text {
                            text: "运行时间:"
                            font.pointSize: 11
                            color: "#666"
                        }
                        Text {
                            id: runtimeText
                            text: "--"
                            font.pointSize: 11
                            font.bold: true
                            color: "#333"
                        }
                        
                        Text {
                            text: "系统状态:"
                            font.pointSize: 11
                            color: "#666"
                        }
                        Text {
                            id: systemStatusText
                            text: "正常"
                            font.pointSize: 11
                            font.bold: true
                            color: successColor
                        }
                    }
                }
            }
        }
    }
}