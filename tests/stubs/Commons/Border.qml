pragma Singleton
import QtQuick

QtObject {
    function surfaceSpec(section, token, color, width) { return {color: color, width: width} }
}
