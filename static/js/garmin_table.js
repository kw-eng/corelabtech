function loadGarminTable(session_id){

fetch(`/api/fit_timeseries/${encodeURIComponent(session_id)}?limit=500`)
.then(res=>res.json())
.then(data=>{

let tbody = document.querySelector("#garminTable tbody")
tbody.innerHTML = ""

let rows = []

for(let i=0;i<data.time.length;i++){

rows.push(`
<tr>
<td>${data.time[i]}</td>
<td>${data.pulse[i] || ""}</td>
<td>${data.spo2[i] || ""}</td>
</tr>
`)

}

tbody.innerHTML = rows.join("")
})
}
