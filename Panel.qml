import QtQuick
import qs.Commons
import qs.Ui
import "Palette.js" as Palette

Panel {
  id: root
  moduleName: "com.sovchat.omarchy"
  ipcTarget: "com.sovchat.omarchy"
  manageIpc: false
  property var anchorItem: null
  property var hostWidget: null
  readonly property var service: hostWidget ? hostWidget.sovchat : null
  onOpenedChanged: if (!opened) content.clearSensitive()

  function persistTheme(value) {
    if (!Palette.valid(value)) return
    var entry = { id: root.moduleName }
    for (var key in root.settings) if (key !== "id") entry[key] = root.settings[key]
    entry.themeId = value
    root.settings = entry
    if (root.hostWidget) root.hostWidget.settings = entry
    if (root.bar && root.bar.shell && typeof root.bar.shell.updateEntryInline === "function")
      root.bar.shell.updateEntryInline(root.moduleName, entry)
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.hostWidget || root
    bar: root.bar
    open: root.opened
    padding: 0
    focusTarget: content.preferredFocus
    contentWidth: panel.fittedContentWidth(Style.space(352))
    contentHeight: panel.fittedContentHeight(Style.space(654))
    CompactView {
      id: content
      anchors.fill: parent
      service: root.service
      uiScale: Style.space(100) / 100
      fontFamily: Style.fontFamily
      themeId: Palette.selected(root.setting("themeId", "ember-shift")).id
      onThemeSelected: function(value) { root.persistTheme(value) }
      onCloseRequested: root.close()
    }
  }
}
