import QtQuick
import Quickshell
import qs.Commons
import qs.Ui as Ui
import qs.Commons as Commons

Ui.Panel {
  id: root
  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }
  moduleName: "io.github.tangonine.omarchy-nas"
  manageIpc: false
  property var anchorItem: null
  property var hostWidget: null
  property var backend: null
  property bool editing: false
  property string oldId: ""
  property var originalMount: ({})
  property bool nfsMode: false
  property bool autoUnmount: true
  readonly property color panelForeground: Commons.Color.foreground

  onOpenedChanged: { if (!opened) { passwordField.value = ""; usernameField.value = ""; domainField.value = "" } }

  function open() { root.controller.show(); if (backend) backend.refresh() }
  function close() { root.controller.hide(); passwordField.value = ""; usernameField.value = ""; domainField.value = "" }
  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function") return root.bar.switchPanelFrom(root.hostWidget || root, direction)
    return false
  }
  function safeId(name) {
    var s = String(name || "nas").toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "")
    return s || "nas"
  }
  function currentUser() {
    return Quickshell.env("USER") || ""
  }
  function clearForm() {
    originalMount = ({}); oldId = ""; nameField.value = ""; idField.value = ""; serverField.value = ""; shareField.value = ""
    mountField.value = "/mnt/nas/"; networkField.value = backend && backend.activeConnections.length ? String(backend.activeConnections[0]) : ""
    userField.value = currentUser(); usernameField.value = ""; passwordField.value = ""; domainField.value = ""
    nfsMode = false; autoUnmount = true
  }
  function editMount(m) {
    originalMount = m; oldId = String(m.id || ""); nameField.value = String(m.name || ""); idField.value = String(m.id || "")
    serverField.value = String(m.server || ""); shareField.value = String(m.share || ""); mountField.value = String(m.mountpoint || "")
    networkField.value = m.networks && m.networks.length ? String(m.networks[0]) : ""; userField.value = String(m.owner || currentUser())
    usernameField.value = ""; passwordField.value = ""; domainField.value = ""; nfsMode = String(m.type) === "nfs"
    autoUnmount = m.auto_unmount !== false; editing = true
  }
  function saveForm() {
    var id = idField.value.trim() || safeId(nameField.value)
    if (!nameField.value.trim() || !serverField.value.trim() || !shareField.value.trim() || !mountField.value.trim() || !networkField.value.trim()) {
      backend.lastError = "Name, server, share, mount point and network are required"; return
    }
    var accepted = backend.saveMount({
      old_id: oldId, id: id, name: nameField.value.trim(), type: nfsMode ? "nfs" : "cifs",
      server: serverField.value.trim(), share: shareField.value.trim(), mountpoint: mountField.value.trim(), owner: userField.value.trim(),
      networks: originalMount.networks && originalMount.networks[0] === networkField.value.trim() ? originalMount.networks : [networkField.value.trim()], auto_unmount: autoUnmount,
      username: usernameField.value, password: passwordField.value, domain: domainField.value,
      options: originalMount.options || []
    })
    if (accepted) passwordField.value = ""
  }

  Connections {
    target: backend
    function onActionFinished(ok, action) {
      if (ok && action === "save") { root.editing = false; root.clearForm() }
      if (ok && action === "delete") root.editing = false
    }
  }

  component ActionButton: Rectangle {
    property string label: strings.t("text.1")
    enabled: true
    signal clicked()
    implicitHeight: Style.space(34); radius: Style.space(6)
    color: enabled ? Qt.rgba(root.panelForeground.r, root.panelForeground.g, root.panelForeground.b, 0.12) : Qt.rgba(root.panelForeground.r, root.panelForeground.g, root.panelForeground.b, 0.05)
    Text { textFormat: Text.PlainText; anchors.centerIn: parent; text: parent.label; color: root.panelForeground; opacity: parent.enabled ? 1 : 0.4; font.family: root.bar ? root.bar.fontFamily : Style.font.family; font.pixelSize: Style.font.body }
    MouseArea { anchors.fill: parent; enabled: parent.enabled; cursorShape: Qt.PointingHandCursor; onClicked: parent.clicked() }
  }

  component FormField: Column {
    id: field
    property string label: ""
    property alias value: input.text
    property bool password: false
    width: parent ? parent.width : Style.space(440)
    spacing: Style.space(4)
    Text { textFormat: Text.PlainText; text: field.label; color: root.panelForeground; opacity: 0.72; font.family: root.bar ? root.bar.fontFamily : Style.font.family; font.pixelSize: Style.font.caption }
    Rectangle {
      width: parent.width; implicitHeight: Style.space(36); radius: Style.space(5); color: Qt.rgba(root.panelForeground.r, root.panelForeground.g, root.panelForeground.b, 0.09)
      TextInput {
        id: input; anchors.fill: parent; anchors.margins: Style.space(8); color: root.panelForeground
        font.family: root.bar ? root.bar.fontFamily : Style.font.family; font.pixelSize: Style.font.body
        echoMode: field.password ? TextInput.Password : TextInput.Normal; verticalAlignment: TextInput.AlignVCenter; clip: true
        selectByMouse: true
      }
    }
  }

  Ui.KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem; owner: root.hostWidget || root; bar: root.bar; open: root.opened; focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(480))
    // Keep the popup usable on laptop/small displays. The contents scroll when
    // the Add/Edit form is taller than the available panel viewport.
    contentHeight: panel.fittedContentHeight(Math.min(panelContent.implicitHeight, Style.space(610)))

    Ui.PanelKeyCatcher {
      id: keyCatcher; anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Flickable {
        id: scroller
        anchors.fill: parent
        clip: true
        contentWidth: width
        contentHeight: panelContent.implicitHeight
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height

        Column {
          id: panelContent; width: scroller.width - (scrollThumb.visible ? Style.space(8) : 0); spacing: Style.space(10)
        Text { textFormat: Text.PlainText; width: parent.width; text: root.editing ? (root.oldId ? strings.t("ui.16") : strings.t("ui.17")) : strings.t("ui.18"); color: root.panelForeground; font.family: root.bar ? root.bar.fontFamily : Style.font.family; font.pixelSize: Style.font.subtitle; font.bold: true }

        Column {
          visible: !root.editing; width: parent.width; spacing: Style.space(9)
          Text { textFormat: Text.PlainText; width: parent.width; text: backend ? ("Network: " + backend.network + "\nStatus: " + backend.stateText) : "Backend unavailable"; color: root.panelForeground; opacity: 0.82; font.family: root.bar ? root.bar.fontFamily : Style.font.family; font.pixelSize: Style.font.body; wrapMode: Text.WordWrap }

          Repeater {
            model: backend ? backend.mounts : []
            delegate: Rectangle {
              required property var modelData
              width: panelContent.width; implicitHeight: details.implicitHeight + Style.space(18); radius: Style.space(6); color: Qt.rgba(root.panelForeground.r, root.panelForeground.g, root.panelForeground.b, 0.08)
              Column {
                id: details; anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; anchors.margins: Style.space(9); spacing: Style.space(6)
                Row {
                  width: parent.width; spacing: Style.space(8)
                  Column {
                    width: parent.width - controls.width - Style.space(10)
                    Text { textFormat: Text.PlainText; width: parent.width; text: String(modelData.name || modelData.id) + (modelData.mounted ? "  ✓" : ""); color: root.panelForeground; font.family: root.bar ? root.bar.fontFamily : Style.font.family; font.pixelSize: Style.font.body; font.bold: true; elide: Text.ElideRight }
                    Text { textFormat: Text.PlainText; width: parent.width; text: String(modelData.type).toUpperCase() + "  " + String(modelData.server) + "/" + String(modelData.share); color: root.panelForeground; opacity: 0.68; font.family: root.bar ? root.bar.fontFamily : Style.font.family; font.pixelSize: Style.font.caption; elide: Text.ElideMiddle }
                    Text { textFormat: Text.PlainText; width: parent.width; text: String(modelData.mountpoint); color: root.panelForeground; opacity: 0.58; font.family: root.bar ? root.bar.fontFamily : Style.font.family; font.pixelSize: Style.font.caption; elide: Text.ElideMiddle }
                  }
                  Row {
                    id: controls; spacing: Style.space(5)
                    ActionButton { implicitWidth: Style.space(64); label: modelData.mounted ? strings.t("ui.34") : strings.t("ui.35"); enabled: backend && backend.canAct && !backend.busy; onClicked: modelData.mounted ? backend.unmountOne(String(modelData.id)) : backend.mountOne(String(modelData.id)) }
                    ActionButton { implicitWidth: Style.space(48); label: strings.t("text.2"); enabled: backend && backend.canAct && !backend.busy; onClicked: root.editMount(modelData) }
                    ActionButton { implicitWidth: Style.space(52); label: strings.t("text.3"); enabled: backend && backend.canAct && !backend.busy; onClicked: backend.deleteMount(String(modelData.id)) }
                  }
                }
              }
            }
          }

          ActionButton { width: parent.width; label: strings.t("text.4"); enabled: backend && backend.canAct && !backend.busy; onClicked: { root.clearForm(); root.editing = true } }
          Row {
            width: parent.width; spacing: Style.space(8)
            ActionButton { implicitWidth: (parent.width - parent.spacing * 2) / 3; label: strings.t("text.5"); enabled: backend && backend.canAct && !backend.busy && backend.mounts.length > 0; onClicked: backend.mountAll() }
            ActionButton { implicitWidth: (parent.width - parent.spacing * 2) / 3; label: strings.t("text.6"); enabled: backend && backend.canAct && !backend.busy && backend.mounts.length > 0; onClicked: backend.unmountAll() }
            ActionButton { implicitWidth: (parent.width - parent.spacing * 2) / 3; label: strings.t("text.7"); enabled: backend && backend.canAct && !backend.busy; onClicked: backend.refresh() }
          }
        }

        Column {
          visible: root.editing; width: parent.width; spacing: Style.space(7)
          FormField { id: nameField; label: strings.t("text.8") }
          FormField { id: idField; label: strings.t("text.9") }
          Row {
            width: parent.width; spacing: Style.space(8)
            ActionButton { implicitWidth: (parent.width - parent.spacing) / 2; label: root.nfsMode ? strings.t("ui.19") : strings.t("ui.20"); onClicked: root.nfsMode = false }
            ActionButton { implicitWidth: (parent.width - parent.spacing) / 2; label: root.nfsMode ? strings.t("ui.21") : strings.t("ui.22"); onClicked: root.nfsMode = true }
          }
          FormField { id: serverField; label: strings.t("text.10") }
          FormField { id: shareField; label: root.nfsMode ? strings.t("ui.23") : strings.t("ui.24") }
          FormField { id: mountField; label: strings.t("text.11") }
          FormField { id: networkField; label: strings.t("text.12") }
          ActionButton { width: parent.width; label: backend && backend.activeConnections.length ? "Use current network: " + String(backend.activeConnections[0]) : strings.t("ui.25"); enabled: backend && backend.activeConnections.length > 0; onClicked: networkField.value = String(backend.activeConnections[0]) }
          FormField { id: userField; label: strings.t("text.13") }
          FormField { id: usernameField; visible: !root.nfsMode; label: oldId ? strings.t("ui.26") : strings.t("ui.27") }
          FormField { id: passwordField; visible: !root.nfsMode; label: oldId ? strings.t("ui.28") : strings.t("ui.29"); password: true }
          FormField { id: domainField; visible: !root.nfsMode; label: strings.t("text.14") }
          ActionButton { width: parent.width; label: root.autoUnmount ? strings.t("ui.30") : strings.t("ui.31"); onClicked: root.autoUnmount = !root.autoUnmount }
          Row {
            width: parent.width; spacing: Style.space(8)
            ActionButton { implicitWidth: (parent.width - parent.spacing) / 2; label: strings.t("text.15"); enabled: !backend || !backend.busy; onClicked: { root.editing = false; root.clearForm() } }
            ActionButton { implicitWidth: (parent.width - parent.spacing) / 2; label: backend && backend.busy ? strings.t("ui.32") : strings.t("ui.33"); enabled: backend && backend.canAct && !backend.busy; onClicked: root.saveForm() }
          }
        }

          Text { textFormat: Text.PlainText; visible: backend && backend.lastError !== ""; width: parent.width; text: backend ? backend.lastError : ""; color: root.panelForeground; opacity: 0.95; font.family: root.bar ? root.bar.fontFamily : Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }
          Text { textFormat: Text.PlainText; visible: backend && backend.lastError === "" && backend.lastMessage !== ""; width: parent.width; text: backend ? backend.lastMessage : ""; color: root.panelForeground; opacity: 0.72; font.family: root.bar ? root.bar.fontFamily : Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }
        }

      }

      // Lightweight themed scrollbar without pulling in QtQuick.Controls.
      Rectangle {
        id: scrollThumb
        visible: scroller.contentHeight > scroller.height + 1
        width: Style.space(3)
        radius: width / 2
        anchors.right: parent.right
        anchors.rightMargin: Style.space(1)
        y: visible ? (scroller.contentY / Math.max(1, scroller.contentHeight - scroller.height)) * (scroller.height - height) : 0
        height: visible ? Math.max(Style.space(28), scroller.height * scroller.height / scroller.contentHeight) : 0
        color: Qt.rgba(root.panelForeground.r, root.panelForeground.g, root.panelForeground.b, 0.45)
      }
    }
  }
}
