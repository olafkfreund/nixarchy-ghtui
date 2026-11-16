pragma Singleton
import QtQuick

QtObject {
    property real cornerRadius: 8
    property real gapsOut: 10
    function space(px) { return px }
    readonly property QtObject font: QtObject {
        property real body: 16
        property real caption: 13
        property real title: 20
        property string menuFamily: "sans-serif"
    }
    readonly property QtObject spacing: QtObject {
        property real hairline: 1
        property real sm: 6
        property real md: 12
        property real panelPadding: 16
    }
}
