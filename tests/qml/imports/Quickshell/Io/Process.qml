import QtQuick
QtObject {
  property bool running: false
  property bool stdinEnabled: false
  property var command: []
  property QtObject stdout: null
  property QtObject stderr: null
  property string received: ""
  signal started()
  signal exited(int exitCode, int exitStatus)
  signal error(int error)
  function write(value) { received += value }
}
