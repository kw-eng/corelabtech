async function runAI(){

let r = await fetch("/ai/run-last")

let data = await r.json()

document.getElementById("ai_result").innerHTML = `
<h3>AI Analysis</h3>
<p>Risk: ${data.risk}</p>
<p>${data.message}</p>
`
}