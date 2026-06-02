async function loadTelemetry(){

let r = await fetch("/api/telemetry")

let d = await r.json()

document.getElementById("pressure").innerText = d.pressure
document.getElementById("spo2").innerText = d.spo2
document.getElementById("pulse").innerText = d.pulse
document.getElementById("hrv").innerText = d.hrv
document.getElementById("temperature").innerText = d.temperature

document.getElementById("ai").innerText =
d.analysis.risk + " | " + d.analysis.message

if(d.spo2 < 90){

document.getElementById("alarm").innerText =
" HYPOXIA ALERT"

}else{

document.getElementById("alarm").innerText=""

}

}

setInterval(loadTelemetry,2000)