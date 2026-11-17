pragma Singleton
import QtQuick

QtObject {
    property color background: "#101315"
    property color accent: "#7aa2f7"
    property color urgent: "#a55555"
    readonly property var menu: ({background: "#1a1b26", border: "#414868", text: "#c0caf5", selectedBackground: "#33467c", selectedText: "#ffffff"})
}
