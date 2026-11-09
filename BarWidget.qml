import QtQuick
import Quickshell
import qs.Ui as Ui
import "UiText.js" as UiText

Ui.BarWidget {
  id: root
  moduleName: "io.github.tangonine.omarchy-nas"

  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function toggle() { if (panelLoader.item) panelLoader.item.toggle() }
  function closeForPopoutSwitch() { if (panelLoader.item) panelLoader.item.closeForPopoutSwitch() }

  function injectPanel() {
    if (!panelLoader.item) return
    panelLoader.item.bar = root.bar
    panelLoader.item.anchorItem = button
    panelLoader.item.hostWidget = root
    panelLoader.item.backend = backend
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight
  onBarChanged: injectPanel()

  readonly property var backend: root.bar && root.bar.shell ? root.bar.shell.serviceFor(root.moduleName) : null
  function configureBackend() {
    if (backend) backend.refreshIntervalSec = Math.max(2, Math.min(60, Number(root.setting("refreshIntervalSec", 5)) || 5))
    injectPanel()
  }
  onBackendChanged: configureBackend()
  onSettingsChanged: configureBackend()

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  Ui.WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.backend ? root.backend.statusGlyph : "󰌙"
    tooltipText: UiText.tooltip("NAS: " + (root.backend ? root.backend.stateText + " — " + root.backend.network : "Service unavailable"))
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.LeftButton) root.toggle()
      else if (buttonCode === Qt.MiddleButton && root.backend) root.backend.refresh()
    }
  }
}
