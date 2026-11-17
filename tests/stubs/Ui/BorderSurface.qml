import QtQuick

Rectangle {
    property var borderSpec: null
    property real padding: 0
    readonly property real contentTopInset: (borderSpec ? borderSpec.width : 0) + padding
    readonly property real contentRightInset: (borderSpec ? borderSpec.width : 0) + padding
    readonly property real contentBottomInset: (borderSpec ? borderSpec.width : 0) + padding
    readonly property real contentLeftInset: (borderSpec ? borderSpec.width : 0) + padding
}
