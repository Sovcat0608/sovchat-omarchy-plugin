import QtQuick
import "Palette.js" as Palette

QtObject {
  property real scale: 1
  property string fontFamily: "monospace"
  property string themeId: "ember-shift"
  readonly property var palette: Palette.selected(themeId)
  readonly property string layoutMode: "compact"
  readonly property color background: Palette.mix(palette.bottom, "#080a0b", 0.84)
  readonly property color sunken: Palette.mix(palette.bottom, "#050607", 0.68)
  readonly property color foreground: "#e8e8e8"
  readonly property color muted: "#898386"
  readonly property color accent: palette.accent
  readonly property color secondary: palette.secondary
  readonly property color raised: Palette.mix("#ffffff", String(background), 0.08)
  readonly property color selected: Palette.mix(palette.accent, String(background), 0.14)
  readonly property color border: Palette.mix("#ffffff", String(background), 0.24)
  readonly property color subtleBorder: Palette.mix("#ffffff", String(background), 0.12)
  readonly property color danger: "#ff7b7b"
  function px(value) { return Math.max(1, Math.round(value * scale)) }
}
