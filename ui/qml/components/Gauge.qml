import QtQuick 2.15

Item {
    id: gauge

    // ✅ 建议的最小尺寸
    implicitWidth: 120
    implicitHeight: 120

    // 公开属性
    property string title: "参数"
    property string unit: ""
    property real minValue: 0
    property real maxValue: 100
    property real value: 50
    property color gaugeColor: "#2196F3"
    property color backgroundColor: "#FAFAFA"
    property color borderColor: "#E0E0E0"
    property real needleWidth: 3
    property int tickCount: 5
    property string valueFormat: "0.1f"

    // ✅ 修正：响应式高度计算
    readonly property real titleHeight: Math.max(20, height * 0.15)
    readonly property real valueHeight: Math.max(25, height * 0.2)
    readonly property real borderWidth: 2

    // ✅ 修正：基于实际可用区域计算表盘参数
    readonly property real dialAreaHeight: height - titleHeight - valueHeight
    readonly property real availableRadius: Math.min(width, dialAreaHeight) / 2 - borderWidth - 10
    readonly property real outerRadius: Math.max(20, availableRadius) // 确保最小半径
    readonly property real tickRadius: outerRadius * 0.9
    readonly property real labelRadius: outerRadius * 0.7
    readonly property real needleLength: outerRadius * 0.85

    // ✅ 修正：基于dialArea的中心点
    readonly property real dialCenterX: width / 2
    readonly property real dialCenterY: dialAreaHeight / 2

    // 角度范围
    readonly property real startAngle: -135
    readonly property real endAngle: 135
    readonly property real totalAngle: endAngle - startAngle

    // ✅ 背景容器
    Rectangle {
        id: background
        anchors.fill: parent
        color: backgroundColor
        border.color: borderColor
        border.width: borderWidth
        radius: Math.min(width, height) * 0.1
    }

    // ✅ 标题区域
    Item {
        id: titleArea
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: titleHeight

        Text {
            id: titleText
            anchors.centerIn: parent
            text: gauge.title
            font.pixelSize: Math.max(10, gauge.height * 0.08)
            font.weight: Font.Medium
            color: "#546E7A"
            horizontalAlignment: Text.AlignHCenter
        }
    }

    // ✅ 表盘区域
    Item {
        id: dialArea
        anchors.top: titleArea.bottom
        anchors.bottom: valueArea.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: 5

        // 刻度盘背景
        Canvas {
            id: dialCanvas
            anchors.fill: parent
            antialiasing: true


            onPaint: {
                var ctx = getContext("2d");
                ctx.reset();
                var centerX = width / 2;
                var centerY = height / 2;
                var maxRadius = Math.min(width, height) / 2 - 15;
                var useRadius = Math.max(outerRadius, maxRadius); 

                // 绘制外圆弧
                ctx.beginPath();
                ctx.arc(centerX, centerY, useRadius, startAngle * Math.PI / 180, endAngle * Math.PI / 180);
                ctx.strokeStyle = "#EEEEEE";
                ctx.lineWidth = 3;
                ctx.stroke();

                // 绘制刻度线和标签
                drawTicks(ctx, centerX, centerY, useRadius);
            }

            function drawTicks(ctx) {
                var steps = Math.max(2, gauge.tickCount);

                for (var i = 0; i < steps; i++) {
                    var ratio = i / (steps - 1);
                    var angle = (startAngle + totalAngle * ratio) * Math.PI / 180;

                    // 刻度线
                    var tickStartX = centerX + tickRadius * Math.cos(angle);
                    var tickStartY = centerY + tickRadius * Math.sin(angle);
                    var tickEndX = centerX + (tickRadius - 10) * Math.cos(angle);
                    var tickEndY = centerY + (tickRadius - 10) * Math.sin(angle);

                    ctx.beginPath();
                    ctx.moveTo(tickStartX, tickStartY);
                    ctx.lineTo(tickEndX, tickEndY);
                    ctx.strokeStyle = "#BDBDBD";
                    ctx.lineWidth = 2;
                    ctx.stroke();

                    // 刻度值（只在首尾和中间显示）
                    if (i === 0 || i === steps - 1 || (steps > 4 && i === Math.floor(steps / 2))) {
                        var value = gauge.minValue + (gauge.maxValue - gauge.minValue) * ratio;
                        var labelX = centerX + labelRadius * Math.cos(angle);
                        var labelY = centerY + labelRadius * Math.sin(angle);

                        ctx.font = `${Math.max(8, gauge.height * 0.06)}px Arial`;
                        ctx.fillStyle = "#757575";
                        ctx.textAlign = "center";
                        ctx.textBaseline = "middle";
                        ctx.fillText(value.toFixed(1), labelX, labelY);
                    }
                }
            }

            // 重绘条件
            Component.onCompleted: requestPaint()
            onWidthChanged: if (visible)
                requestPaint()
            onHeightChanged: if (visible)
                requestPaint()

            Connections {
                target: gauge
                function onTickCountChanged() {
                    dialCanvas.requestPaint();
                }
                function onMinValueChanged() {
                    dialCanvas.requestPaint();
                }
                function onMaxValueChanged() {
                    dialCanvas.requestPaint();
                }
            }
        }

        // ✅ 指针
        Item {
            id: needleContainer
            anchors.centerIn: parent
            width: needleLength * 2
            height: needleLength * 2

            Rectangle {
                id: needle
                width: Math.max(gauge.needleWidth, 2)
                height: needleLength
                radius: width / 2
                color: gauge.gaugeColor
                transformOrigin: Item.Bottom
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: needleLength / 2

                // ✅ 角度计算
                rotation: {
                    var range = gauge.maxValue - gauge.minValue;
                    if (range <= 0)
                        return startAngle;

                    var normalizedValue = Math.max(0, Math.min(1, (gauge.value - gauge.minValue) / range));
                    return startAngle + totalAngle * normalizedValue;
                }

                Behavior on rotation {
                    NumberAnimation {
                        duration: 300
                        easing.type: Easing.OutCubic
                    }
                }
            }

            // 中心圆点
            Rectangle {
                width: Math.max(8, gauge.width * 0.05)
                height: width
                radius: width / 2
                color: gauge.gaugeColor
                anchors.centerIn: parent

                // 添加光晕效果
                Rectangle {
                    anchors.centerIn: parent
                    width: parent.width + 4
                    height: parent.height + 4
                    radius: width / 2
                    color: "transparent"
                    border.color: Qt.lighter(gauge.gaugeColor, 1.3)
                    border.width: 1
                    opacity: 0.5
                }
            }
        }
    }

    // ✅ 数值显示区域
    Item {
        id: valueArea
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        height: valueHeight

        Text {
            id: valueText
            anchors.centerIn: parent
            font.pixelSize: Math.max(12, gauge.height * 0.1)
            font.weight: Font.Bold
            color: "#212121"
            horizontalAlignment: Text.AlignHCenter

            text: {
                var n = Number(gauge.value);
                if (isNaN(n))
                    return "--";

                var formattedValue;
                if (gauge.valueFormat === "%") {
                    formattedValue = (n * 100).toFixed(1) + "%";
                } else {
                    var match = gauge.valueFormat.match(/(\d+)\.(\d+)f/);
                    var digits = match ? parseInt(match[2]) : 1;
                    formattedValue = n.toFixed(digits);
                }

                return formattedValue + (gauge.unit ? " " + gauge.unit : "");
            }
        }

        // 数值背景
        Rectangle {
            anchors.centerIn: valueText
            width: valueText.contentWidth + 16
            height: valueText.contentHeight + 8
            color: Qt.lighter(gauge.backgroundColor, 0.95)
            border.color: "#E8E8E8"
            border.width: 1
            radius: 4
            z: -1
        }
    }
}
