import QtQuick

Item {
    property string moduleName: ""
    property var bar: null
    readonly property bool vertical: bar ? !!bar.vertical : false
}
