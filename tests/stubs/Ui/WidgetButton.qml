import QtQuick

Item {
    property var bar: null
    property string text: ""
    property bool active: false
    property bool dimmed: false
    property string tooltipText: ""
    property int pressFeedbackButtons: 0
    signal pressed(int button)
    implicitWidth: 100
    implicitHeight: 32
    function triggerPress(button) { pressed(button) }
}
