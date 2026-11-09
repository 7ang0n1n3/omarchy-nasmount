import QtQuick
import QtTest
import "../.." as Plugin
import "../../UiText.js" as UiText

TestCase {
  name: "NasService"
  Component { id: factory; Plugin.Service { alive: false } }
  property var service
  function init() { service = createTemporaryObject(factory, this); verify(service !== null) }
  function deliver(operation, output, code) {
    service.alive = true
    service.operation = operation; service.output = output; service.completed = false
    service.complete(code || 0)
    service.alive = false
  }
  function test_tooltip_neutralizes_markup() {
    compare(UiText.tooltip('<img src="https://example.invalid">&日本語'), '&lt;img src="https://example.invalid"&gt;&amp;日本語')
  }
  function test_output_overflow() {
    service.appendOutput("x".repeat(262145), false)
    verify(service.overflow); compare(service.output, "")
  }
  function test_failed_action_survives_refresh() {
    service.errors = "Mount failed"
    deliver("mount", "", 1)
    deliver("status", '{"protocol_version":1,"mounts":[],"active_connections":[],"known_connections":[]}')
    compare(service.lastError, "Mount failed")
  }
  function test_stdin_and_overlap() {
    service.alive = true; service.supported = true; service.state = "ready"
    verify(service.saveMount({password:"fictional-secret", name:"日本語"}))
    var process = findChild(service, "nasProcess")
    verify(process !== null)
    compare(process.command.join(" "), "omarchy-nasctl save --stdin")
    verify(!service.saveMount({password:"second"}))
    process.started()
    verify(process.received.indexOf("fictional-secret") >= 0)
    compare(service.pendingJson, ""); verify(!process.stdinEnabled)
    service.alive = false; process.running = false
  }
  function test_payload_limit() {
    service.alive=true; service.supported=true; service.state="ready"
    verify(!service.saveMount({password:"x".repeat(17000)}))
    verify(!service.busy); service.alive=false
  }
  function test_status_states_data() {
    return [
      {tag:"empty", mounts:[], active:[], expected:"empty"},
      {tag:"ready", mounts:[{id:"a", mounted:true, has_credentials:true}], active:["Home"], expected:"ready"},
      {tag:"offline", mounts:[{id:"a",mounted:false,has_credentials:true}], active:[], expected:"offline"},
      {tag:"credentials", mounts:[{id:"a",mounted:false,has_credentials:false}], active:["Home"], expected:"unauthenticated"},
      {tag:"partial", mounts:[{id:"a",mounted:true},{id:"b",mounted:false}], active:["Home"], expected:"partial"}
    ]
  }
  function test_status_states(data) {
    deliver("status",JSON.stringify({protocol_version:1, mounts:data.mounts, active_connections:data.active, known_connections:[]}))
    compare(service.state,data.expected)
  }
  function test_malformed_clears_stale() {
    service.mounts = [{id:"stale",mounted:true}]; service.mountedCount = 1
    deliver("status","bad json")
    compare(service.state,"failed"); compare(service.mounts.length,0); compare(service.mountedCount,0)
  }
  function test_unsupported() {
    deliver("capabilities",'{"protocol_version":0}')
    compare(service.state,"unsupported"); verify(!service.canAct)
  }
  function test_unauthorized() {
    service.errors = "sudo: a password is required"
    deliver("status","",1)
    compare(service.state,"unauthorized"); verify(!service.canAct)
  }
  function test_no_completion_after_disable() {
    service.operation="status"; service.output='{}'; service.completed=false
    service.complete(0)
    compare(service.state,"loading")
  }
  function test_duplicate_completion_ignored() {
    deliver("status","bad json")
    service.alive=true; service.state="offline"; service.complete(0)
    compare(service.state,"offline"); service.alive=false
  }
}
