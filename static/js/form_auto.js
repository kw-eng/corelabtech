function previewSession(){

let user = document.getElementById("user_id").value

fetch(`/api/next_session/${user}`)
.then(res=>res.json())
.then(data=>{
document.getElementById("session_id").value =
`${user}_S${String(data.next).padStart(3,'0')}`
})
}