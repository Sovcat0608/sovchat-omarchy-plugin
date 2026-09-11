import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "com.sovchat.omarchy"
  readonly property var sovchat: bar && bar.shell ? bar.shell.serviceFor(moduleName) : null
  readonly property bool opened: panelLoader.item ? panelLoader.item.opened : false
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing : false
  readonly property real openPanelIndicatorWidth: Style.bar.iconCanvas
  readonly property real openPanelIndicatorHeight: Math.max(Style.space(10), Math.round(Style.bar.iconSlot * 0.55))
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight
  CompactTheme { id: theme; themeId: root.setting("themeId", "ember-shift") }

  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function toggle() { if (panelLoader.item) panelLoader.item.toggle() }
  function closeForPopoutSwitch() { if (panelLoader.item) panelLoader.item.closeForPopoutSwitch() }
  function injectPanel() {
    if (!panelLoader.item) return
    panelLoader.item.bar = bar
    panelLoader.item.settings = settings
    panelLoader.item.anchorItem = button
    panelLoader.item.hostWidget = root
  }
  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()
  Loader {
    id: panelLoader
    active: true
    visible: false
    source: Qt.resolvedUrl("Panel.qml")
    onLoaded: { root.injectPanel(); Qt.callLater(root.injectPanel) }
  }
  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    active: !!root.sovchat && root.sovchat.media.connected
    tooltipText: !root.sovchat ? "SovChat requires Omarchy's built-in bar service access"
      : root.sovchat.update.available ? "SovChat plugin update available"
      : root.sovchat.session ? "Open SovChat" : "Sign in to SovChat"
    iconComponent: Component {
      Item {
        Image { anchors.centerIn: parent; width: Style.space(24); height: width; source: "assets/ico.svg"; fillMode: Image.PreserveAspectFit }
        Text { anchors.right: parent.right; anchors.top: parent.top; visible: !!root.sovchat && root.sovchat.update.available; text: "↑"; color: theme.secondary; font.bold: true; font.pixelSize: Style.space(10) }
      }
    }
    onPressed: function(buttonCode) { root.toggle() }
  }
}
