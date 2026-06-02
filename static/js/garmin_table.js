function loadGarminTable(session_id){

fetch(`/api/fit_timeseries/${session_id}`)
.then(res=>res.json())
.then(data=>{

let tbody = document.querySelector("#garminTable tbody")
tbody.innerHTML = ""

for(let i=0;i<data.time.length;i++){

let row = `
<tr>
<td>${data.time[i]}</td>
<td>${data.pulse[i] || ""}</td>
<td>${data.spo2[i] || ""}</td>
</tr>
`

tbody.innerHTML += row
}
})
}