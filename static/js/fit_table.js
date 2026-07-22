function loadFitTable(session_id){
    fetch(`/api/fit_data?session_id=${session_id}`)
        .then(response => response.json())
        .then(data => {
            let tbody = document.querySelector("#fitTable tbody");
            if (!tbody) return;
            tbody.innerHTML = "";
            data.forEach(row => {
                tbody.innerHTML += `<tr><td>${row.timestamp}</td><td>${row.heart_rate}</td></tr>`;
            });
        });
}
