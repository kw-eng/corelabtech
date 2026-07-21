async function parseAdminJson(res, label) {
    const text = await res.text()

    console.log(`${label} RAW RESPONSE:`, text)

    try {
        return JSON.parse(text)
    } catch (e) {
        console.error(`${label} non JSON response`, text)

        return {
            status: "error",
            error: `${label} returned HTML`,
            raw: text
        }
    }
}

function setAccountsStatus(message, type = "info") {
    const box = document.getElementById("accountsStatus")

    if (!box) {
        return
    }

    if (!message) {
        box.innerHTML = ""
        return
    }

    box.innerHTML = `
        <div class="accounts-alert ${type}">
            ${message}
        </div>
    `
}

function updateAccountKpis(accounts) {
    const total = accounts.length
    const active = accounts.filter(account => account.is_active).length
    const admins = accounts.filter(account => account.role === "admin").length

    document.getElementById("accountsTotal").innerText = total
    document.getElementById("accountsActive").innerText = active
    document.getElementById("accountsAdmins").innerText = admins
}

function roleOptions(selectedRole, email) {
    return ["viewer", "operator", "researcher", "admin"].map(role => `
        <option
            value="${role}"
            ${selectedRole === role ? "selected" : ""}
        >
            ${role}
        </option>
    `).join("")
}

function renderAccounts(accounts) {
    const tbody = document.getElementById("accountsBody")

    if (!tbody) {
        console.error("accountsBody not found")
        return
    }

    tbody.innerHTML = ""

    if (!Array.isArray(accounts)) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5">Invalid response</td>
            </tr>
        `
        return
    }

    if (accounts.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5">No accounts found.</td>
            </tr>
        `
        updateAccountKpis([])
        return
    }

    accounts.forEach(account => {
        const activeLabel = account.is_active ? "Active" : "Disabled"

        tbody.innerHTML += `
            <tr>
                <td>
                    <strong>${account.email}</strong>
                </td>

                <td>
                    <select
                        class="accounts-inline-select"
                        onchange="updateRole('${account.email}', this.value)"
                    >
                        ${roleOptions(account.role, account.email)}
                    </select>
                </td>

                <td>
                    <label class="accounts-toggle">
                        <input
                            type="checkbox"
                            ${account.is_active ? "checked" : ""}
                            onchange="toggleActive('${account.email}', this.checked)"
                        >
                        <span>${activeLabel}</span>
                    </label>
                </td>

                <td>${account.created_at || "-"}</td>

                <td>
                    <button
                        class="accounts-secondary"
                        onclick="resetPassword('${account.email}')"
                    >
                        Reset Password
                    </button>
                </td>
            </tr>
        `
    })

    updateAccountKpis(accounts)
}

async function loadAccounts() {
    setAccountsStatus("Loading accounts...", "info")

    try {
        const res = await fetch("/api/admin/accounts", {
            credentials: "same-origin"
        })
        const accounts = await parseAdminJson(res, "LOAD ACCOUNTS")

        if (!res.ok || accounts.error) {
            setAccountsStatus(accounts.error || "Loading accounts failed.", "error")
            renderAccounts([])
            return
        }

        renderAccounts(accounts)
        setAccountsStatus("", "")
    } catch (err) {
        console.error("loadAccounts error", err)
        setAccountsStatus(`Loading accounts crashed: ${err}`, "error")
    }
}

async function createAccount() {
    const email = document.getElementById("account_email").value.trim()
    const password = document.getElementById("account_password").value
    const role = document.getElementById("account_role").value

    if (!email) {
        setAccountsStatus("Enter an email address.", "error")
        return
    }

    if (!password) {
        setAccountsStatus("Enter a temporary password.", "error")
        return
    }

    setAccountsStatus("Creating account...", "info")

    const res = await fetch("/api/admin/accounts", {
        method: "POST",
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            email,
            password,
            role
        })
    })
    const data = await parseAdminJson(res, "CREATE ACCOUNT")

    if (!res.ok || data.error) {
        setAccountsStatus(data.error || "Create account failed.", "error")
        return
    }

    document.getElementById("account_email").value = ""
    document.getElementById("account_password").value = ""
    document.getElementById("account_role").value = "viewer"

    setAccountsStatus("Account created.", "success")
    await loadAccounts()
}

async function resetPassword(email) {
    const password = prompt(`New password for ${email}`)

    if (!password) {
        return
    }

    setAccountsStatus(`Updating password for ${email}...`, "info")

    const res = await fetch("/api/admin/accounts/reset_password", {
        method: "POST",
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            email,
            password
        })
    })
    const data = await parseAdminJson(res, "RESET PASSWORD")

    if (!res.ok || data.error) {
        setAccountsStatus(data.error || "Reset failed.", "error")
        return
    }

    setAccountsStatus("Password updated.", "success")
}

async function updateRole(email, role) {
    setAccountsStatus(`Updating role for ${email}...`, "info")

    const res = await fetch("/api/admin/accounts/update_role", {
        method: "POST",
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            email,
            role
        })
    })
    const data = await parseAdminJson(res, "UPDATE ROLE")

    if (!res.ok || data.error) {
        setAccountsStatus(data.error || "Update role failed.", "error")
        await loadAccounts()
        return
    }

    setAccountsStatus("Role updated.", "success")
    await loadAccounts()
}

async function toggleActive(email, active) {
    setAccountsStatus(`Updating account status for ${email}...`, "info")

    const res = await fetch("/api/admin/accounts/toggle_active", {
        method: "POST",
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            email,
            is_active: active
        })
    })
    const data = await parseAdminJson(res, "TOGGLE ACTIVE")

    if (!res.ok || data.error) {
        setAccountsStatus(data.error || "Update failed.", "error")
        await loadAccounts()
        return
    }

    setAccountsStatus("Account status updated.", "success")
    await loadAccounts()
}

document.addEventListener("DOMContentLoaded", () => {
    loadAccounts()
})
