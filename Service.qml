import QtQuick
import Quickshell
import Quickshell.Io

Item {
  id: root
  property var shell: null
  property var manifest: null
  property string network: "Unknown"
  property string stateText: "Checking…"
  property string state: "loading"
  property string lastError: ""
  property string lastMessage: ""
  property var mounts: []
  property var knownConnections: []
  property var activeConnections: []
  property int mountedCount: 0
  readonly property int totalCount: mounts.length
  property int refreshIntervalSec: 5
  property bool supported: false
  readonly property bool busy: worker.running
  readonly property bool canAct: supported && state !== "unavailable" && state !== "unsupported" && state !== "unauthorized" && state !== "failed"
  readonly property string statusGlyph: mountedCount > 0 ? "󰋊" : "󰌙"
  readonly property string shortText: totalCount === 0 ? "NAS" : mountedCount + "/" + totalCount
  property string operation: ""
  property string pendingJson: ""
  property string output: ""
  property string errors: ""
  property bool overflow: false
  property bool expired: false
  property bool alive: true
  property bool completed: true
  property bool actionError: false
  signal actionFinished(bool ok, string action)

  function launch(action, args, payload) {
    if (!alive || worker.running) return false
    completed = false; operation = action; output = ""; errors = ""; overflow = false; expired = false
    pendingJson = payload || ""
    worker.stdinEnabled = pendingJson !== ""
    worker.command = ["omarchy-nasctl"].concat(args)
    watchdog.restart()
    worker.running = true
    return true
  }
  function refresh() {
    if (busy) return
    launch(supported ? "status" : "capabilities", supported ? ["status", "--json"] : ["capabilities"], "")
  }
  function runAction(action, value) {
    if (!canAct || busy) return false
    actionError = false; lastError = ""; lastMessage = ""
    return launch(action, value ? [action, value] : [action], "")
  }
  function saveMount(data) {
    if (!canAct || busy) return false
    var payload = JSON.stringify(data)
    if (unescape(encodeURIComponent(payload)).length > 16384) { lastError = "Settings payload is too large"; return false }
    actionError = false; lastError = ""; lastMessage = ""
    return launch("save", ["save", "--stdin"], payload)
  }
  function deleteMount(id) { return runAction("delete", id) }
  function mountAll() { return runAction("mount-all", "") }
  function unmountAll() { return runAction("unmount-all", "") }
  function reconcile() { return runAction("reconcile", "") }
  function mountOne(id) { return runAction("mount", id) }
  function unmountOne(id) { return runAction("unmount", id) }
  function appendOutput(chunk, isError) {
    if ((isError ? errors.length : output.length) + chunk.length > 262144) {
      overflow = true; worker.running = false; return
    }
    if (isError) errors += chunk
    else output += chunk
  }
  function unavailable(kind, message) {
    state = kind; stateText = message; lastError = message
    mounts = []; mountedCount = 0; network = "Unknown"; activeConnections = []; knownConnections = []
  }
  function complete(code) {
    if (completed) return
    completed = true
    watchdog.stop(); pendingJson = ""
    if (!alive) return
    var action = operation
    if (code !== 0 || overflow || expired) {
      var message = expired ? "NAS operation timed out; refresh before retrying" : overflow ? "NAS response exceeded its limit" : errors.trim().slice(0, 512) || "NAS helper unavailable; check machine setup"
      if (action === "capabilities") {
        supported = false
        unavailable("unsupported", "Install or upgrade the NAS machine integration (protocol 1)")
      } else if (action === "status") {
        var denied = /sudo:|password is required|not allowed|permission denied/i.test(message)
        unavailable(denied ? "unauthorized" : "failed", denied ? "NAS authorization unavailable; check machine setup" : message)
      } else { actionError = true; lastError = message; actionFinished(false, action) }
    } else {
      try {
        if (action === "capabilities") {
          var cap = JSON.parse(output)
          if (cap.protocol_version !== 1 || cap.save_stdin !== true) throw new Error("Unsupported helper")
          supported = true; state = "loading"; lastError = ""
          Qt.callLater(root.refresh)
        } else if (action === "status") {
          var data = JSON.parse(output)
          if (data.protocol_version !== 1 || !Array.isArray(data.mounts) || data.mounts.length > 128 || !Array.isArray(data.active_connections) || !Array.isArray(data.known_connections)) throw new Error("Invalid status")
          var count = 0, credentialsMissing = false
          for (var i = 0; i < data.mounts.length; ++i) {
            var m = data.mounts[i]
            if (!m || typeof m.id !== "string" || typeof m.mounted !== "boolean") throw new Error("Invalid share")
            if (m.mounted) count++
            if (m.has_credentials === false) credentialsMissing = true
          }
          mounts = data.mounts; mountedCount = count
          network = String(data.network || "Disconnected")
          activeConnections = data.active_connections; knownConnections = data.known_connections
          state = mounts.length === 0 ? "empty" : credentialsMissing ? "unauthenticated" : activeConnections.length === 0 ? "offline" : count === mounts.length ? "ready" : count > 0 ? "partial" : "unmounted"
          stateText = ({empty:"No shares configured", unauthenticated:"SMB credentials required", offline:"Offline", ready:"All mounted", partial:"Partially mounted", unmounted:"Not mounted"})[state]
          if (!actionError) lastError = ""
        } else {
          lastError = ""; lastMessage = action === "save" ? "NAS settings saved" : action === "delete" ? "NAS removed" : "Done"
          actionFinished(true, action)
          if (action === "save") Qt.callLater(root.reconcile)
        }
      } catch (e) {
        supported = action === "capabilities" ? false : supported
        unavailable(action === "capabilities" ? "unsupported" : "failed", "Invalid or unsupported NAS response; upgrade machine integration")
      }
    }
    if (action !== "capabilities" && action !== "status") refreshDelay.restart()
    output = ""; errors = ""
  }
  Process {
    id: worker
    objectName: "nasProcess"
    stdout: SplitParser { splitMarker: ""; onRead: data => root.appendOutput(data, false) }
    stderr: SplitParser { splitMarker: ""; onRead: data => root.appendOutput(data, true) }
    onStarted: {
      if (root.pendingJson !== "") { write(root.pendingJson); root.pendingJson = ""; stdinEnabled = false }
    }
    onExited: (exitCode, exitStatus) => root.complete(exitCode)
    // Process has no error signal; failed starts are handled by finishCheck
    // and the watchdog, including failures without an exited notification.
    onRunningChanged: {
      if (!running && watchdog.running) finishCheck.restart()
    }
  }
  Timer { id: finishCheck; interval: 100; onTriggered: { if (watchdog.running && !worker.running) root.complete(1) } }
  Timer { id: watchdog; interval: 45000; onTriggered: { root.expired = true; root.pendingJson = ""; worker.running = false; root.complete(1) } }
  Timer { id: refreshDelay; interval: 500; onTriggered: root.refresh() }
  Timer {
    interval: root.supported && root.state !== "failed" && root.state !== "unauthorized" ? Math.max(2, Math.min(60, root.refreshIntervalSec)) * 1000 : 60000
    running: true; repeat: true; triggeredOnStart: true
    onTriggered: root.refresh()
  }
  Component.onDestruction: { alive = false; pendingJson = ""; worker.running = false }
}
