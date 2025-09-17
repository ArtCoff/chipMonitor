import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtCharts

Item {
    id: root
    anchors.fill: parent

    // 数据缓存
    property var tempHistory: []
    property var vibHistory: []
    property var focusHistory: []
    property var humidityHistory: []
    property int maxPoints: 100  // 图表视图显示更多点
    property real baseTime: 0
    
    // 颜色主题
    readonly property color primaryColor: "#2196F3"
    readonly property color successColor: "#4CAF50"
    readonly property color warningColor: "#FF9800"
    readonly property color dangerColor: "#F44336"
    readonly property color infoColor: "#9C27B0"

    // ✅ 数据更新函数
    function updateCharts(data) {
        if (!data) return;

        var now = Date.now();
        if (baseTime === 0) {
            baseTime = now;
        }
        var relativeTime = (now - baseTime) / 1000;

        console.log("📊 Chart view updating with data:", JSON.stringify(data));

        // 更新各种数据
        if (data.temperature !== undefined) {
            tempHistory.push({ x: relativeTime, y: data.temperature });
            if (tempHistory.length > maxPoints) tempHistory.shift();
            
            var tempPoints = [];
            for (var i = 0; i < tempHistory.length; i++) {
                tempPoints.push(Qt.point(tempHistory[i].x, tempHistory[i].y));
            }
            temperatureSeries.replace(tempPoints);
        }

        if (data.vibration !== undefined) {
            vibHistory.push({ x: relativeTime, y: data.vibration });
            if (vibHistory.length > maxPoints) vibHistory.shift();
            
            var vibPoints = [];
            for (var i = 0; i < vibHistory.length; i++) {
                vibPoints.push(Qt.point(vibHistory[i].x, vibHistory[i].y));
            }
            vibrationSeries.replace(vibPoints);
        }

        if (data.focus_error !== undefined) {
            focusHistory.push({ x: relativeTime, y: data.focus_error });
            if (focusHistory.length > maxPoints) focusHistory.shift();
            
            var focusPoints = [];
            for (var i = 0; i < focusHistory.length; i++) {
                focusPoints.push(Qt.point(focusHistory[i].x, focusHistory[i].y));
            }
            focusSeries.replace(focusPoints);
        }

        if (data.humidity !== undefined) {
            humidityHistory.push({ x: relativeTime, y: data.humidity });
            if (humidityHistory.length > maxPoints) humidityHistory.shift();
            
            var humidityPoints = [];
            for (var i = 0; i < humidityHistory.length; i++) {
                humidityPoints.push(Qt.point(humidityHistory[i].x, humidityHistory[i].y));
            }
            humiditySeries.replace(humidityPoints);
        }

        updateTimeAxis();
    }
    
    function updateTimeAxis() {
        if (tempHistory.length === 0) return;
        
        var minTime = tempHistory[0].x;
        var maxTime = tempHistory[tempHistory.length - 1].x;
        var timeSpan = maxTime - minTime;
        
        if (timeSpan < 30) {
            maxTime = minTime + 30;
        }
        
        // 更新所有图表的时间轴
        tempAxisX.min = minTime;
        tempAxisX.max = maxTime;
        vibAxisX.min = minTime;
        vibAxisX.max = maxTime;
        focusAxisX.min = minTime;
        focusAxisX.max = maxTime;
        humidityAxisX.min = minTime;
        humidityAxisX.max = maxTime;
    }

    // ✅ 数据连接
    Connections {
        target: dataProcessor
        ignoreUnknownSignals: true

        function onProcessed_data_updated(data) {
            updateCharts(data);
        }
    }

    Component.onCompleted: {
        console.log("🚀 ChartView initialized");
    }

    // ==================== 图表布局 ====================
    GridLayout {
        anchors.fill: parent
        anchors.margins: 15
        columns: 2
        rows: 2
        columnSpacing: 15
        rowSpacing: 15
        
        // ✅ 1. 温度趋势图
        ChartView {
            id: tempChart
            title: "温度趋势 (°C)"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 250
            antialiasing: true
            legend.visible: true
            legend.alignment: Qt.AlignTop
            backgroundColor: "#FAFAFA"
            titleFont.pixelSize: 14
            titleFont.bold: true
            
            ValueAxis {
                id: tempAxisY
                min: 21.0
                max: 23.0
                tickCount: 6
                labelFormat: "%.2f"
                gridVisible: true
                minorGridVisible: true
            }
            
            ValueAxis {
                id: tempAxisX
                min: 0
                max: 60
                tickCount: 7
                labelFormat: "%.0fs"
                titleText: "时间 (秒)"
                gridVisible: true
            }
            
            LineSeries {
                id: temperatureSeries
                name: "温度"
                color: primaryColor
                width: 3
                axisX: tempAxisX
                axisY: tempAxisY
                useOpenGL: true
            }
        }
        
        // ✅ 2. 振动趋势图
        ChartView {
            id: vibChart
            title: "振动趋势 (g)"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 250
            antialiasing: true
            legend.visible: true
            legend.alignment: Qt.AlignTop
            backgroundColor: "#FAFAFA"
            titleFont.pixelSize: 14
            titleFont.bold: true
            
            ValueAxis {
                id: vibAxisY
                min: 0.0
                max: 0.15
                tickCount: 6
                labelFormat: "%.3f"
                gridVisible: true
                minorGridVisible: true
            }
            
            ValueAxis {
                id: vibAxisX
                min: 0
                max: 60
                tickCount: 7
                labelFormat: "%.0fs"
                titleText: "时间 (秒)"
                gridVisible: true
            }
            
            LineSeries {
                id: vibrationSeries
                name: "振动"
                color: warningColor
                width: 3
                axisX: vibAxisX
                axisY: vibAxisY
                useOpenGL: true
            }
        }
        
        // ✅ 3. 对焦误差趋势图
        ChartView {
            id: focusChart
            title: "对焦误差趋势 (μm)"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 250
            antialiasing: true
            legend.visible: true
            legend.alignment: Qt.AlignTop
            backgroundColor: "#FAFAFA"
            titleFont.pixelSize: 14
            titleFont.bold: true
            
            ValueAxis {
                id: focusAxisY
                min: -0.3
                max: 0.3
                tickCount: 7
                labelFormat: "%.3f"
                gridVisible: true
                minorGridVisible: true
            }
            
            ValueAxis {
                id: focusAxisX
                min: 0
                max: 60
                tickCount: 7
                labelFormat: "%.0fs"
                titleText: "时间 (秒)"
                gridVisible: true
            }
            
            LineSeries {
                id: focusSeries
                name: "对焦误差"
                color: dangerColor
                width: 3
                axisX: focusAxisX
                axisY: focusAxisY
                useOpenGL: true
            }
        }
        
        // ✅ 4. 湿度趋势图
        ChartView {
            id: humidityChart
            title: "湿度趋势 (%)"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 250
            antialiasing: true
            legend.visible: true
            legend.alignment: Qt.AlignTop
            backgroundColor: "#FAFAFA"
            titleFont.pixelSize: 14
            titleFont.bold: true
            
            ValueAxis {
                id: humidityAxisY
                min: 30
                max: 70
                tickCount: 6
                labelFormat: "%.1f"
                gridVisible: true
                minorGridVisible: true
            }
            
            ValueAxis {
                id: humidityAxisX
                min: 0
                max: 60
                tickCount: 7
                labelFormat: "%.0fs"
                titleText: "时间 (秒)"
                gridVisible: true
            }
            
            LineSeries {
                id: humiditySeries
                name: "湿度"
                color: infoColor
                width: 3
                axisX: humidityAxisX
                axisY: humidityAxisY
                useOpenGL: true
            }
        }
    }
}