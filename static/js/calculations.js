// Live przeliczenie ATA
function calculateATA(){

let kpa = document.querySelector("[name='pressure_kpa']").value

if(!kpa) return

let ata = (kpa / 101.3).toFixed(2)

document.getElementById("ata_display").innerText = ata + " ATA"
}

function calculateOxygen(){

let lpm = document.querySelector("[name='oxygen_lpm']").value

if(!lpm) return

let percent = 21 + (lpm * 10)

if(percent > 96) percent = 96

document.getElementById("o2_display").innerText = percent + "%"
}
async function loadTests(){

let r = await fetch("/api/admin/tests")
let data = await r.json()

let html = ""

data.forEach(d=>{
html += `
<label>
<input type="checkbox" class="test-checkbox" value="${d.id}">
Session ${d.session_id} | ${d.phase} | SpO2: ${d.spo2}
</label><br>
`
})

document.getElementById("data-list").innerHTML = html

}

loadTests()