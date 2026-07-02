const apiRequest = async (url, options = {}) => {
    const csrfToken = document.querySelector('input[name="_csrf_token"]');
    const headers = {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRFToken": csrfToken.value } : {}),
        ...options.headers,
    };
    const response = await fetch(url, {
        headers,
        credentials: "same-origin",
        ...options,
    });

    const data = await response.json();
    if (!response.ok) {
        // If session expired, redirect to login gracefully
        if (response.status === 401 && !url.includes("/api/login")) {
            console.warn("[Session expired] Redirecting to login...");
            window.location.href = "/login";
            return;
        }
        throw new Error(data.error || "Request failed");
    }
    return data;
};

const escapeHtml = (str) => {
    if (!str) return '';
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(String(str)));
    return div.innerHTML;
};

const setMessage = (element, message, type) => {
    if (!element) return;
    element.textContent = message;
    element.classList.remove("success", "error");
    if (type) {
        element.classList.add(type);
    }
    if (message) {
        showGlobalAlert(message, type || "message");
    }
};

const showGlobalAlert = (message, type = "message") => {
    if (!message) return;

    const stack = document.getElementById("page-alert-stack") || document.querySelector(".auth-alert-stack");
    if (!stack) return;

    const alert = document.createElement("div");
    alert.className = `bank-alert ${type}`;
    alert.dataset.alert = "true";
    alert.innerHTML = `
        <span class="bank-alert-icon" aria-hidden="true">${type === "success" || type === "message" ? "✅" : type === "warning" ? "⚠" : "❌"}</span>
        <span class="bank-alert-text">
            <strong class="bank-alert-title"></strong>
            <span class="bank-alert-body"></span>
        </span>
        <button class="bank-alert-close" type="button" aria-label="Dismiss alert">&times;</button>
    `;
    alert.querySelector(".bank-alert-title").textContent =
        type === "success" || type === "message"
            ? "Operation Successful"
            : type === "warning"
                ? "Please Check Your Input"
                : "Transaction Failed";
    alert.querySelector(".bank-alert-body").textContent = message;

    const closeAlert = () => {
        alert.remove();
    };

    alert.querySelector(".bank-alert-close").addEventListener("click", closeAlert);
    stack.prepend(alert);
    window.setTimeout(closeAlert, 5000);
};

const setupAlertDismissals = () => {
    document.querySelectorAll("[data-alert]").forEach((alert) => {
        const closeButton = alert.querySelector(".bank-alert-close");
        const dismiss = () => alert.remove();

        if (closeButton) {
            closeButton.addEventListener("click", dismiss);
        }

        window.setTimeout(dismiss, 5000);
    });
};

const formatCurrency = (value) => {
    return new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
    }).format(value);
};

const formatTimestamp = (value) => {
    if (!value) return "-";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    const formatter = new Intl.DateTimeFormat("en-IN", {
        timeZone: "Asia/Kolkata",
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
    });
    const parts = formatter.formatToParts(parsed).reduce((acc, part) => {
        acc[part.type] = part.value;
        return acc;
    }, {});
    return `${parts.day} ${parts.month} ${parts.year}, ${parts.hour}:${parts.minute} ${parts.dayPeriod} IST`;
};

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const setButtonLoading = (button, isLoading, label = "Processing...") => {
    if (!button) return;
    if (isLoading) {
        button.dataset.originalLabel = button.textContent;
        button.textContent = label;
        button.disabled = true;
        return;
    }
    if (button.dataset.originalLabel) {
        button.textContent = button.dataset.originalLabel;
        delete button.dataset.originalLabel;
    }
    button.disabled = false;
};

const setNavUserName = (name) => {
    const navName = document.getElementById("nav-user-name");
    if (navName && name) {
        navName.textContent = name;
    }
};

const getAccountId = () => {
    return localStorage.getItem("account_id") || "";
};

const setAccountId = (accountId) => {
    localStorage.setItem("account_id", accountId);
};

const clearAccountId = () => {
    localStorage.removeItem("account_id");
};

const hydrateNavUser = () => {
    const navName = document.getElementById("nav-user-name");
    const accountId = getAccountId();
    if (!navName || !accountId) return;
    if (navName.textContent && navName.textContent !== "Guest") return;

    apiRequest(`/api/account/${accountId}`)
        .then((data) => {
            setNavUserName(data.name || "Customer");
        })
        .catch(() => {
            setNavUserName("Customer");
        });
};

const setupCreateAccount = () => {
    const form = document.getElementById("create-account-form");
    const message = document.getElementById("create-message");

    if (!form) return;

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        setMessage(message, "");

        const payload = {
            name: form.name.value.trim(),
            email: form.email.value.trim(),
            account_type: form.account_type.value,
            initial_deposit: form.initial_deposit.value,
        };

        try {
            const button = form.querySelector("button[type='submit']");
            setButtonLoading(button, true);
            const data = await Promise.all([
                apiRequest("/api/create_account", {
                method: "POST",
                body: JSON.stringify(payload),
                }),
                delay(500),
            ]).then(([result]) => result);
            setAccountId(data.account_id);
            setMessage(message, "Account created successfully!", "success");
            window.location.href = "/dashboard";
        } catch (error) {
            setMessage(message, error.message, "error");
        } finally {
            const button = form.querySelector("button[type='submit']");
            setButtonLoading(button, false);
        }
    });
};

const setupSignup = () => {
    const form = document.getElementById("signup-form");
    const message = document.getElementById("signup-message");

    if (!form) return;

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        setMessage(message, "");

        const payload = {
            name: form.name.value.trim(),
            email: form.email.value.trim(),
            password: form.password.value,
        };

        const confirmInput = form.querySelector("[name='confirm_password']");
        if (confirmInput && confirmInput.value !== form.password.value) {
            setMessage(message, "Passwords do not match.", "error");
            return;
        }

        try {
            const button = form.querySelector("button[type='submit']");
            setButtonLoading(button, true);
            const data = await Promise.all([
                apiRequest("/api/signup", {
                method: "POST",
                body: JSON.stringify(payload),
                }),
                delay(500),
            ]).then(([result]) => result);
            setMessage(
                message,
                "Signup successful. Check the console for verification link.",
                "success"
            );
            if (data.verification_link) {
            }
            window.location.href = "/login";
        } catch (error) {
            setMessage(message, error.message, "error");
        } finally {
            const button = form.querySelector("button[type='submit']");
            setButtonLoading(button, false);
        }
    });
};

const setupLogin = () => {
    const form = document.getElementById("login-form");
    const message = document.getElementById("login-message");

    if (!form) return;

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        setMessage(message, "");

        const payload = {
            email: form.email.value.trim(),
            password: form.password.value,
        };

        try {
            const button = form.querySelector("button[type='submit']");
            setButtonLoading(button, true);
            const data = await Promise.all([
                apiRequest("/api/login", {
                method: "POST",
                body: JSON.stringify(payload),
                }),
                delay(500),
            ]).then(([result]) => result);
            setAccountId(data.account_id);
            setMessage(message, "Login successful!", "success");
            window.location.href = "/dashboard";
        } catch (error) {
            setMessage(message, error.message, "error");
        } finally {
            const button = form.querySelector("button[type='submit']");
            setButtonLoading(button, false);
        }
    });
};

const setupLoginFlash = () => {
    const container = document.querySelector("[data-page='login']");
    if (!container) return;

    const flash = container.querySelector(".flash-message");
    if (!flash) return;

    if (flash.classList.contains("error")) {
        const card = container.querySelector(".auth-card");
        const inputs = container.querySelectorAll("input");
        if (card) {
            card.classList.remove("shake");
            void card.offsetWidth;
            card.classList.add("shake");
        }
        inputs.forEach((input) => input.classList.add("input-error"));
    }

    setTimeout(() => {
        flash.classList.add("hide");
    }, 4000);
};

const setupThemeToggle = () => {
    const toggle = document.getElementById("theme-toggle");
    if (!toggle) return;

    const updateLabel = () => {
        const isDark = document.documentElement.classList.contains("dark-mode");
        toggle.textContent = isDark ? "☀️ Light Mode" : "🌙 Dark Mode";
        toggle.setAttribute("aria-pressed", isDark ? "true" : "false");
    };

    updateLabel();

    toggle.addEventListener("click", () => {
        const isDark = document.documentElement.classList.toggle("dark-mode");
        localStorage.setItem("theme", isDark ? "dark" : "light");
        updateLabel();
    });
};

const setupForgotPassword = () => {
    const form = document.getElementById("forgot-form");
    const message = document.getElementById("forgot-message");

    if (!form) return;

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        setMessage(message, "");

        try {
            const button = form.querySelector("button[type='submit']");
            setButtonLoading(button, true);
            const data = await Promise.all([
                apiRequest("/api/password/forgot", {
                method: "POST",
                body: JSON.stringify({ email: form.email.value.trim() }),
                }),
                delay(500),
            ]).then(([result]) => result);
            setMessage(message, "If the email exists, a reset link was created.", "success");
            if (data.reset_link) {
            }
        } catch (error) {
            setMessage(message, error.message, "error");
        } finally {
            const button = form.querySelector("button[type='submit']");
            setButtonLoading(button, false);
        }
    });
};

const setupResetPassword = () => {
    const form = document.getElementById("reset-form");
    const message = document.getElementById("reset-message");
    const container = document.querySelector("[data-page='reset']");

    if (!form || !container) return;

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        setMessage(message, "");

        try {
            const button = form.querySelector("button[type='submit']");
            setButtonLoading(button, true);
            await Promise.all([
                apiRequest("/api/password/reset", {
                method: "POST",
                body: JSON.stringify({
                    token: container.dataset.token,
                    password: form.password.value,
                }),
                }),
                delay(500),
            ]);
            setMessage(message, "Password updated. Please login.", "success");
            window.location.href = "/login";
        } catch (error) {
            setMessage(message, error.message, "error");
        } finally {
            const button = form.querySelector("button[type='submit']");
            setButtonLoading(button, false);
        }
    });
};

const renderTransactions = (rows, transactions) => {
    if (!transactions.length) {
        rows.innerHTML = "<tr><td colspan='4' class='text-center'>No transactions yet.</td></tr>";
        return;
    }

    rows.innerHTML = transactions
        .map((tx) => {
            const statusLabel = tx.status || "Completed";
            let typeLabel = tx.type
                ? `${tx.type.charAt(0).toUpperCase()}${tx.type.slice(1)}`
                : "-";
            const dateLabel = tx.formatted_time || formatTimestamp(tx.timestamp);
            
            // Classification & Styling
            let icon = "🔔";
            let iconClass = "general";
            let amountClass = "amount-transfer";
            let amountPrefix = "";
            let titleLabel = "Transaction";

            const meta = tx.metadata || {};
            
            if (tx.type === "deposit") {
                icon = "📥";
                iconClass = "deposit";
                amountClass = "amount-credit";
                amountPrefix = "+";
                titleLabel = "Cash Deposit";
            } else if (tx.type === "withdraw") {
                icon = "📤";
                iconClass = "withdraw";
                amountClass = "amount-debit";
                amountPrefix = "-";
                titleLabel = "Cash Withdrawal";
            } else if (tx.type === "transfer") {
                icon = "💸";
                iconClass = "transfer";
                amountClass = "amount-transfer";
                
                if (meta.from_account_id) {
                    amountPrefix = "+";
                    titleLabel = `Transfer Received`;
                    if (meta.sender_name) {
                        titleLabel += ` from ${meta.sender_name}`;
                    }
                } else if (meta.to_account_id) {
                    amountPrefix = "-";
                    titleLabel = `Transfer Sent`;
                    if (meta.receiver_name) {
                        titleLabel += ` to ${meta.receiver_name}`;
                    }
                } else {
                    titleLabel = "Account Transfer";
                }
            }

            return `
                <tr>
                    <td>
                        <div class="tx-details-cell">
                            <div class="tx-icon-wrap ${iconClass}" aria-hidden="true">${icon}</div>
                            <div>
                                <strong class="tx-title">${escapeHtml(titleLabel)}</strong>
                                <span class="tx-subtitle">${escapeHtml(dateLabel)} <span class="divider">•</span> ID: ${escapeHtml(tx.transaction_id || "-")}</span>
                            </div>
                        </div>
                    </td>
                    <td><span class="type-badge ${tx.type || 'general'}">${typeLabel}</span></td>
                    <td><span class="status-badge ${statusLabel.toLowerCase()}">${statusLabel}</span></td>
                    <td class="text-right">
                        <strong class="amount-val ${amountClass}">${amountPrefix}${formatCurrency(tx.amount)}</strong>
                    </td>
                </tr>
            `;
        })
        .join("");
};

const setupTransactions = () => {
    const container = document.querySelector("[data-page='transactions']");
    if (!container) return;

    const accountId = container.dataset.accountId || getAccountId();
    const rows = document.getElementById("transaction-rows");
    const message = document.getElementById("transactions-message");
    const filtersForm = document.getElementById("transaction-filters");
    const exportCsv = document.getElementById("export-csv");
    const exportPdf = document.getElementById("export-pdf");
    const prevBtn = document.getElementById("transactions-prev");
    const nextBtn = document.getElementById("transactions-next");
    const pageLabel = document.getElementById("transactions-page");

    let currentPage = 1;
    const pageLimit = 10;

    // Date preset helpers (1m,3m,6m,1y,all)
    const startInput = document.getElementById("filter-start");
    const endInput = document.getElementById("filter-end");
    const presetButtons = Array.from((filtersForm || document).querySelectorAll(".preset-pill"));

    const formatDate = (d) => d.toISOString().split("T")[0];
    const applyPreset = (range) => {
        const today = new Date();
        let start = null;
        if (range === "all") {
            if (startInput) startInput.value = "";
            if (endInput) endInput.value = "";
            return;
        }
        if (range === "1m") start = new Date(today.getFullYear(), today.getMonth() - 1, today.getDate());
        if (range === "3m") start = new Date(today.getFullYear(), today.getMonth() - 3, today.getDate());
        if (range === "6m") start = new Date(today.getFullYear(), today.getMonth() - 6, today.getDate());
        if (range === "1y") start = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate());
        if (startInput && start) startInput.value = formatDate(start);
        if (endInput) endInput.value = formatDate(today);
        
        // auto-apply
        const params = new URLSearchParams(new FormData(filtersForm || undefined));
        fetchTransactions(`?${params.toString()}`, 1);
    };

    if (presetButtons.length) {
        presetButtons.forEach((btn) => {
            btn.addEventListener("click", (e) => {
                presetButtons.forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
                const r = btn.dataset.range;
                applyPreset(r);
            });
        });
    }

    if (!accountId) {
        if (rows) rows.innerHTML = "<tr><td colspan='4' class='text-center'>Please login first.</td></tr>";
        return;
    }

    const fetchTransactions = (queryString = "", page = currentPage) => {
        if (rows) {
            rows.innerHTML = "<tr><td colspan='4' class='text-center'>Processing...</td></tr>";
        }
        apiRequest(`/api/transactions/${accountId}${queryString}&page=${page}&limit=${pageLimit}`)
            .then((data) => {
                renderTransactions(rows, data.transactions);
                currentPage = data.page;
                if (pageLabel) {
                    pageLabel.textContent = `Page ${data.page} of ${data.total_pages}`;
                }
                if (prevBtn) prevBtn.disabled = !data.has_prev;
                if (nextBtn) nextBtn.disabled = !data.has_next;

                // Update Summaries
                const summary = data.summary || {};
                const totalTxEl = document.getElementById("summary-total-tx");
                const totalDepositsEl = document.getElementById("summary-total-deposits");
                const totalWithdrawalsEl = document.getElementById("summary-total-withdrawals");
                const balanceEl = document.getElementById("summary-balance");
                const infoEl = document.getElementById("transactions-info");

                if (totalTxEl) totalTxEl.textContent = summary.total_transactions || 0;
                if (totalDepositsEl) totalDepositsEl.textContent = formatCurrency(summary.total_deposits || 0);
                if (totalWithdrawalsEl) totalWithdrawalsEl.textContent = formatCurrency(summary.total_withdrawals || 0);
                if (balanceEl) balanceEl.textContent = formatCurrency(summary.current_balance || 0);

                if (infoEl) {
                    infoEl.textContent = `Showing ${data.transactions.length} of ${data.total} transactions`;
                }

                // Render Chart
                renderTransactionsChart(summary);
            })
            .catch((error) => {
                setMessage(message, error.message, "error");
            });
    };

    let txChart = null;
    const renderTransactionsChart = (summary) => {
        const canvas = document.getElementById("transactions-chart");
        if (!canvas) return;

        if (txChart) txChart.destroy();

        const ctx = canvas.getContext("2d");
        txChart = new Chart(ctx, {
            type: "bar",
            data: {
                labels: ["Deposits (Credits)", "Withdrawals (Debits)"],
                datasets: [{
                    label: "Transaction Volume (₹)",
                    data: [summary.total_deposits || 0, summary.total_withdrawals || 0],
                    backgroundColor: [
                        "rgba(34, 197, 94, 0.6)",
                        "rgba(239, 68, 68, 0.6)"
                    ],
                    borderColor: [
                        "rgb(34, 197, 94)",
                        "rgb(239, 68, 68)"
                    ],
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: (value) => "₹" + value.toLocaleString()
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    };

    fetchTransactions("?", 1);

    if (filtersForm) {
        filtersForm.addEventListener("submit", (event) => {
            event.preventDefault();
            const params = new URLSearchParams(new FormData(filtersForm));
            fetchTransactions(`?${params.toString()}`, 1);
        });
    }

    const resetBtn = document.getElementById("btn-reset-filters");
    if (resetBtn) {
        resetBtn.addEventListener("click", () => {
            if (filtersForm) filtersForm.reset();
            presetButtons.forEach(b => b.classList.remove("active"));
            const allPill = presetButtons.find(b => b.dataset.range === "all");
            if (allPill) allPill.classList.add("active");
            fetchTransactions("?", 1);
        });
    }

    if (prevBtn) {
        prevBtn.addEventListener("click", () => {
            const params = new URLSearchParams(new FormData(filtersForm || undefined));
            fetchTransactions(`?${params.toString()}`, Math.max(1, currentPage - 1));
        });
    }

    if (nextBtn) {
        nextBtn.addEventListener("click", () => {
            const params = new URLSearchParams(new FormData(filtersForm || undefined));
            fetchTransactions(`?${params.toString()}`, currentPage + 1);
        });
    }

    if (exportCsv) {
        exportCsv.addEventListener("click", (event) => {
            event.preventDefault();
            const params = new URLSearchParams(new FormData(filtersForm || undefined));
            const qs = params.toString() ? `?${params.toString()}` : "";
            window.location.href = `/api/transactions/${accountId}/export/csv${qs}`;
        });
    }

    if (exportPdf) {
        exportPdf.addEventListener("click", (event) => {
            event.preventDefault();
            const params = new URLSearchParams(new FormData(filtersForm || undefined));
            const qs = params.toString() ? `?${params.toString()}` : "";
            window.location.href = `/api/transactions/${accountId}/export/pdf${qs}`;
        });
    }
};

const setupDashboard = () => {
    const container = document.querySelector("[data-page='dashboard']");
    if (!container) return;

    const accountId = container.dataset.accountId || getAccountId();
    
    const nameEl = document.getElementById("account-name");
    const emailEl = document.getElementById("account-email");
    const typeEl = document.getElementById("account-type");
    const balanceEl = document.getElementById("account-balance");
    const balanceSub = document.querySelector(".balance-sub");
    const message = document.getElementById("dashboard-message");
    const deleteBtn = document.getElementById("delete-account");
    const recentList = document.getElementById("recent-transactions");
    const notificationList = document.getElementById("notification-list");
    const notificationPrev = document.getElementById("notifications-prev");
    const notificationNext = document.getElementById("notifications-next");
    const notificationPage = document.getElementById("notifications-page");
    let notificationCurrentPage = 1;
    const notificationLimit = 5;

    if (!accountId) {
        console.error("No account ID found. Redirecting to create account.");
        setMessage(message, "No account found. Redirecting to create account...", "error");
        setTimeout(() => {
            window.location.href = "/create";
        }, 1500);
        return;
    }

    apiRequest(`/api/account/${accountId}`)
        .then((data) => {
            if (nameEl) nameEl.textContent = data.name;
            if (emailEl) emailEl.textContent = data.email;
            if (typeEl) typeEl.textContent = `Account Type: ${data.account_type || "-"}`;
            if (balanceEl) balanceEl.textContent = formatCurrency(data.balance);
            if (balanceSub) {
                balanceSub.textContent = `Updated ${formatTimestamp(new Date())}`;
            }
            setNavUserName(data.name);
        })
        .catch((error) => {
            console.error("Failed to load account:", error);
            setMessage(message, `Failed to load account: ${error.message}`, "error");
        });

    apiRequest(`/api/transactions/${accountId}`)
        .then((data) => {
            if (!recentList) return;
            const slice = data.transactions.slice(0, 5);
            if (!slice.length) {
                recentList.innerHTML = "<li>No recent transactions.</li>";
                return;
            }
            recentList.innerHTML = slice
                .map(
                    (tx) =>
                        `<li>${escapeHtml(tx.type)} ${formatCurrency(tx.amount)} <span class="meta">${
                            escapeHtml(tx.formatted_time || formatTimestamp(tx.timestamp))
                        }</span></li>`
                )
                .join("");
        })
        .catch(() => {
            if (recentList) recentList.innerHTML = "<li>Unable to load.</li>";
        });

    const fetchNotifications = (page = notificationCurrentPage) => {
        apiRequest(`/api/notifications?page=${page}&limit=${notificationLimit}`)
            .then((data) => {
                if (!notificationList) return;
                notificationCurrentPage = data.page;
                if (!data.notifications.length) {
                    notificationList.innerHTML = "<li>No notifications yet.</li>";
                } else {
                    notificationList.innerHTML = data.notifications
                        .map((note) => {
                            const isWarning = note.level === "warning";
                            const msg = note.message || "";
                            const metadata = note.metadata || {};
                            const hasEmailPreview = Boolean(metadata.email_preview_html);
                            const type = metadata.type || "";
                            let icon = "🔔";
                            if (isWarning) icon = "⚠️";
                            else if (hasEmailPreview) icon = "📧";
                            else if (type === "transfer" || msg.toLowerCase().includes("transfer")) icon = "📤";
                            else if (type === "deposit" || msg.toLowerCase().includes("deposit")) icon = "➕";
                            else if (type === "withdraw" || msg.toLowerCase().includes("withdraw")) icon = "➖";
                            const timeLabel = note.created_at_display || formatTimestamp(note.created_at);
                            const emailBadge = hasEmailPreview
                                ? "<span class=\"email-badge\">Email Notification Sent</span>"
                                : "";
                            const emailPreview = hasEmailPreview
                                ? `<details class="email-preview">
                                        <summary>View email preview</summary>
                                        <div class="email-preview-body">${metadata.email_preview_html}</div>
                                   </details>`
                                : "";
                            const typeClass = type ? ` ${type}` : "";
                            return `<li class="notification-item${typeClass} ${isWarning ? 'warning' : ''}">
                                <span class="notif-icon">${icon}</span>
                                <div class="notif-body">
                                    <span class="notif-message">${escapeHtml(msg)}</span>
                                    ${emailBadge}
                                    ${emailPreview}
                                    <span class="notif-time">${escapeHtml(timeLabel)}</span>
                                </div>
                            </li>`;
                        })
                        .join("");
                }
                if (notificationPage) {
                    notificationPage.textContent = `Page ${data.page} of ${data.total_pages}`;
                }
                if (notificationPrev) notificationPrev.disabled = !data.has_prev;
                if (notificationNext) notificationNext.disabled = !data.has_next;
            })
            .catch(() => {
                if (notificationList) notificationList.innerHTML = "<li>Unable to load.</li>";
            });
    };

    // Migrate old notifications with ObjectIds once per session, then fetch
    const migrationKey = "notifications_migrated";
    if (!sessionStorage.getItem(migrationKey)) {
        const csrfMig = document.querySelector('input[name="_csrf_token"]');
        fetch("/api/notifications/migrate", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", ...(csrfMig ? { "X-CSRFToken": csrfMig.value } : {}) },
        })
            .then(() => {
                sessionStorage.setItem(migrationKey, "1");
                fetchNotifications();
            })
            .catch(() => {
                fetchNotifications();
            });
    } else {
        fetchNotifications();
    }

    if (notificationPrev) {
        notificationPrev.addEventListener("click", () => {
            fetchNotifications(Math.max(1, notificationCurrentPage - 1));
        });
    }

    if (notificationNext) {
        notificationNext.addEventListener("click", () => {
            fetchNotifications(notificationCurrentPage + 1);
        });
    }

    if (deleteBtn) {
        deleteBtn.addEventListener("click", async () => {
            if (!confirm("Delete this account and all transactions?")) return;
            try {
                await apiRequest(`/api/account/${accountId}`, { method: "DELETE" });
                clearAccountId();
                window.location.href = "/";
            } catch (error) {
                setMessage(message, error.message, "error");
            }
        });
    }
};

const setupTransact = () => {
    const depositForm = document.getElementById("deposit-form");
    const withdrawForm = document.getElementById("withdraw-form");
    const transferForm = document.getElementById("transfer-form");
    const depositMessage = document.getElementById("deposit-message");
    const withdrawMessage = document.getElementById("withdraw-message");
    const transferMessage = document.getElementById("transfer-message");

    if (!depositForm || !withdrawForm || !transferForm) return;

    depositForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        setMessage(depositMessage, "");

        const pin = depositForm.pin ? depositForm.pin.value.trim() : "";
        if (!pin) {
            setMessage(depositMessage, "Transaction PIN is required.", "error");
            return;
        }

        try {
            const button = depositForm.querySelector("button[type='submit']");
            setButtonLoading(button, true);
            const data = await Promise.all([
                apiRequest("/api/deposit", {
                method: "POST",
                body: JSON.stringify({
                    amount: depositForm.amount.value,
                    pin: pin,
                }),
                }),
                delay(450),
            ]).then(([result]) => result);
            setMessage(
                depositMessage,
                `${data.message || "Amount deposited successfully."} New balance: ${formatCurrency(data.balance)}`,
                "success"
            );
            depositForm.reset();
        } catch (error) {
            if (error.message.includes("PIN not set")) {
                setMessage(depositMessage, error.message, "error");
                window.location.href = "/setup-pin";
                return;
            }
            setMessage(depositMessage, error.message, "error");
        } finally {
            const button = depositForm.querySelector("button[type='submit']");
            setButtonLoading(button, false);
        }
    });

    withdrawForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        setMessage(withdrawMessage, "");

        const pin = withdrawForm.pin ? withdrawForm.pin.value.trim() : "";
        if (!pin) {
            setMessage(withdrawMessage, "Transaction PIN is required.", "error");
            return;
        }

        try {
            const button = withdrawForm.querySelector("button[type='submit']");
            setButtonLoading(button, true);
            const csrfW = document.querySelector('input[name="_csrf_token"]');
            const data = await Promise.all([
                fetch("/api/withdraw", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: { "Content-Type": "application/json", ...(csrfW ? { "X-CSRFToken": csrfW.value } : {}) },
                    body: JSON.stringify({
                        amount: withdrawForm.amount.value,
                        pin: pin,
                    }),
                }).then(async (response) => {
                    const payload = await response.json();
                    if (!response.ok) {
                        if (payload.require_pin_setup) {
                            const setupUrl = payload.setup_url || "/setup-pin";
                            const error = new Error("PIN not set. Please set your transaction PIN.");
                            error.setupUrl = setupUrl;
                            throw error;
                        }
                        throw new Error(payload.error || "Request failed");
                    }
                    return payload;
                }),
                delay(450),
            ]).then(([result]) => result);
            setMessage(
                withdrawMessage,
                `${data.message || "Amount withdrawn successfully."} New balance: ${formatCurrency(data.balance)}`,
                "success"
            );
            withdrawForm.reset();
        } catch (error) {
            if (error.setupUrl || error.message.includes("PIN not set")) {
                setMessage(withdrawMessage, error.message, "error");
                window.location.href = error.setupUrl || "/setup-pin";
                return;
            }
            setMessage(withdrawMessage, error.message, "error");
        } finally {
            const button = withdrawForm.querySelector("button[type='submit']");
            setButtonLoading(button, false);
        }
    });

    transferForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        setMessage(transferMessage, "");

        const pin = transferForm.pin ? transferForm.pin.value.trim() : "";
        if (!pin) {
            setMessage(transferMessage, "Transaction PIN is required.", "error");
            return;
        }

        try {
            const button = transferForm.querySelector("button[type='submit']");
            setButtonLoading(button, true);
            const csrfT = document.querySelector('input[name="_csrf_token"]');
            const data = await Promise.all([
                fetch("/api/transfer", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: { "Content-Type": "application/json", ...(csrfT ? { "X-CSRFToken": csrfT.value } : {}) },
                    body: JSON.stringify({
                        receiver_email: transferForm.receiver_email.value.trim(),
                        amount: transferForm.amount.value,
                        pin: pin,
                    }),
                }).then(async (response) => {
                    const payload = await response.json();
                    if (!response.ok) {
                        if (payload.require_pin_setup) {
                            const setupUrl = payload.setup_url || "/setup-pin";
                            const error = new Error("PIN not set. Please set your transaction PIN.");
                            error.setupUrl = setupUrl;
                            throw error;
                        }
                        throw new Error(payload.error || "Request failed");
                    }
                    return payload;
                }),
                delay(450),
            ]).then(([result]) => result);
            setMessage(
                transferMessage,
                `${data.message || "Money transferred successfully."} New balance: ${formatCurrency(data.balance)}`,
                "success"
            );
            transferForm.reset();
        } catch (error) {
            if (error.setupUrl || error.message.includes("PIN not set")) {
                setMessage(transferMessage, error.message, "error");
                window.location.href = error.setupUrl || "/setup-pin";
                return;
            }
            setMessage(transferMessage, error.message, "error");
        } finally {
            const button = transferForm.querySelector("button[type='submit']");
            setButtonLoading(button, false);
        }
    });
};

const setupTransferPage = () => {
    const container = document.querySelector("[data-page='transfer']");
    if (!container) return;

    const accountId = container.dataset.accountId || getAccountId();
    const balanceEl = document.getElementById("transfer-balance");
    const emailInput = document.getElementById("receiverEmail");
    const beneficiarySelect = document.getElementById("beneficiarySelect");
    const amountInput = document.getElementById("transferAmount");
    const pinInput = document.getElementById("transferPin");
    const transferBtn = document.getElementById("transferBtn");
    const statusMsg = document.getElementById("statusMsg");
    const quickButtons = container.querySelectorAll("[data-amount]");

    if (!accountId) {
        setMessage(statusMsg, "No account found. Please log in.", "error");
        if (transferBtn) transferBtn.disabled = true;
        return;
    }

    apiRequest(`/api/account/${accountId}`)
        .then((data) => {
            if (balanceEl) balanceEl.textContent = formatCurrency(data.balance || 0);
            const timeEl = document.getElementById("balance-updated-time");
            if (timeEl) {
                timeEl.textContent = `Updated ${formatTimestamp(new Date())}`;
            }
        })
        .catch((error) => {
            setMessage(statusMsg, error.message, "error");
        });

    if (quickButtons.length && amountInput) {
        quickButtons.forEach((button) => {
            button.addEventListener("click", () => {
                amountInput.value = button.dataset.amount;
            });
        });
    }

    // populate beneficiary select
    if (beneficiarySelect) {
        fetchBeneficiaries().then(list => {
            beneficiarySelect.innerHTML = '<option value="">-- Choose saved beneficiary --</option>' + list.map(b => {
                const label = b.nickname ? escapeHtml(b.nickname) + ' ('+escapeHtml(b.name)+')' : escapeHtml(b.name);
                return `<option value="${escapeHtml(b.email)}">${label} — ${escapeHtml(b.email)}</option>`;
            }).join('');
            // if quick_transfer_email exists, prefill
            const quick = sessionStorage.getItem('quick_transfer_email');
            if (quick) {
                emailInput.value = quick;
                sessionStorage.removeItem('quick_transfer_email');
            }
        }).catch(()=>{});

        beneficiarySelect.addEventListener('change', (e) => {
            const val = e.target.value || '';
            if (emailInput) emailInput.value = val;
        });
    }

    if (transferBtn) {
        transferBtn.addEventListener("click", async () => {
            const receiverEmail = emailInput?.value.trim();
            const amount = amountInput?.value.trim();
            const pin = pinInput?.value.trim();
            const scheduleCheck = document.getElementById("scheduleCheck");
            const scheduleAt = document.getElementById("scheduleAt");

            if (!receiverEmail || !amount || !pin) {
                setMessage(statusMsg, "All fields are required.", "error");
                return;
            }

            setMessage(statusMsg, "", "");
            setButtonLoading(transferBtn, true, "Processing...");

            try {
                // If scheduling is requested, call scheduled-transfers API
                if (scheduleCheck && scheduleCheck.checked) {
                    const payload = {
                        receiver_email: receiverEmail,
                        amount: amount,
                        pin: pin,
                        scheduled_at: scheduleAt && scheduleAt.value ? new Date(scheduleAt.value).toISOString() : null,
                    };
                    const csrfEl = document.querySelector('input[name="_csrf_token"]');
                    const csrfVal = csrfEl ? csrfEl.value : '';
                    const resp = await fetch("/api/scheduled-transfers", {
                        method: "POST",
                        credentials: "same-origin",
                        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfVal },
                        body: JSON.stringify(payload),
                    });
                    const data = await resp.json();
                    if (!resp.ok) throw new Error(data.error || data.message || "Unable to schedule transfer");
                    setMessage(statusMsg, "Transfer scheduled.", "success");
                    if (amountInput) amountInput.value = "";
                    return;
                }

                const csrfEl2 = document.querySelector('input[name="_csrf_token"]');
                const csrfVal2 = csrfEl2 ? csrfEl2.value : '';
                const response = await fetch("/api/transfer", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: { "Content-Type": "application/json", "X-CSRFToken": csrfVal2 },
                    body: JSON.stringify({
                        receiver_email: receiverEmail,
                        amount: amount,
                        pin: pin,
                    }),
                });
                const data = await response.json();
                if (!response.ok) {
                    if (data.require_pin_setup) {
                        const setupUrl = data.setup_url || "/setup-pin";
                        const error = new Error("PIN not set. Please set your transaction PIN.");
                        error.setupUrl = setupUrl;
                        throw error;
                    }
                    throw new Error(data.error || "Request failed");
                }

                setMessage(statusMsg, "Transfer successful!", "success");
                if (amountInput) amountInput.value = "";
                if (pinInput) pinInput.value = "";
                if (balanceEl && data.balance !== undefined) {
                    balanceEl.textContent = formatCurrency(data.balance);
                }
            } catch (error) {
                if (error.setupUrl || error.message.includes("PIN not set")) {
                    setMessage(statusMsg, error.message, "error");
                    window.location.href = error.setupUrl || "/setup-pin";
                    return;
                }
                setMessage(statusMsg, error.message, "error");
            } finally {
                setButtonLoading(transferBtn, false);
            }
        });
    }
};

const setupSetPin = () => {
    const form = document.getElementById("set-pin-form");
    if (!form) return;

    const pinInput = document.getElementById("pin");
    const confirmInput = document.getElementById("confirm-pin");
    const message = document.getElementById("set-pin-message");

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        setMessage(message, "", "");

        const pin = pinInput ? pinInput.value.trim() : "";
        const confirmPin = confirmInput ? confirmInput.value.trim() : "";

        if (!pin || !confirmPin) {
            setMessage(message, "Please enter and confirm your PIN.", "error");
            return;
        }
        if (pin !== confirmPin) {
            setMessage(message, "PIN entries do not match.", "error");
            return;
        }
        if (!/^\d{4}$/.test(pin)) {
            setMessage(message, "PIN must be exactly 4 digits.", "error");
            return;
        }

        const button = form.querySelector("button[type='submit']");
        setButtonLoading(button, true, "Saving...");

        try {
            const data = await apiRequest("/api/set-pin", {
                method: "POST",
                body: JSON.stringify({ pin: pin }),
            });
            setMessage(message, data.message || "PIN set successfully.", "success");
            setTimeout(() => {
                window.location.href = "/dashboard";
            }, 800);
        } catch (error) {
            setMessage(message, error.message, "error");
        } finally {
            setButtonLoading(button, false);
        }
    });
};

const setupChangePassword = () => {
    const container = document.querySelector('[data-page="security"]');
    if (!container) return;
    const form = document.getElementById('change-password-form');
    const message = document.getElementById('change-password-message');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        setMessage(message, '', '');
        const current = (document.getElementById('current-password') || {}).value || '';
        const nw = (document.getElementById('new-password') || {}).value || '';
        const confirm = (document.getElementById('confirm-password') || {}).value || '';
        if (!current || !nw || !confirm) {
            setMessage(message, 'All fields are required.', 'error');
            return;
        }
        if (nw !== confirm) {
            setMessage(message, 'New passwords do not match.', 'error');
            return;
        }
        if (nw.length < 8) {
            setMessage(message, 'New password must be at least 8 characters.', 'error');
            return;
        }
        const btn = form.querySelector('button[type=submit]');
        setButtonLoading(btn, true, 'Updating...');
        try {
            const data = await apiRequest('/api/change-password', { method: 'POST', body: JSON.stringify({ current, new: nw, confirm }) });
            setMessage(message, data.message || 'Password changed. Please login again.', 'success');
            setTimeout(() => { window.location.href = '/login'; }, 900);
        } catch (err) {
            setMessage(message, err.message, 'error');
        } finally {
            setButtonLoading(btn, false);
        }
    });
};

// Beneficiaries: fetch, render, add, delete
const fetchBeneficiaries = async () => {
    try {
        const data = await apiRequest('/api/beneficiaries');
        return data.beneficiaries || [];
    } catch (err) {
        return [];
    }
};

const renderBeneficiariesList = (container, list) => {
    const target = container.querySelector('#beneficiaries-list');
    if (!target) return;
    if (!list.length) {
        target.innerHTML = '<p>No beneficiaries saved.</p>';
        return;
    }
    target.innerHTML = list.map(b => {
        const nameDisplay = b.nickname ? escapeHtml(b.nickname) + ' (' + escapeHtml(b.name) + ')' : escapeHtml(b.name);
        return `
        <div class="beneficiary-card" data-id="${escapeHtml(b.id)}">
            <div class="benef-row">
                <div>
                    <strong>${nameDisplay}</strong>
                    <div class="muted">${escapeHtml(b.email)}</div>
                </div>
                <div class="benef-actions">
                    <button class="btn ghost quick-transfer" data-email="${escapeHtml(b.email)}">Transfer</button>
                    <button class="btn danger delete-benef" data-id="${escapeHtml(b.id)}">Delete</button>
                </div>
            </div>
        </div>`;
    }).join('');
};

const setupBeneficiaries = () => {
    const container = document.querySelector('[data-page="beneficiaries"]');
    if (!container) return;
    const form = document.getElementById('beneficiary-form');
    const message = document.getElementById('benef-message');

    const refresh = async () => {
        const list = await fetchBeneficiaries();
        renderBeneficiariesList(container, list);
        // also populate transfer select if present
        const select = document.getElementById('beneficiarySelect');
        if (select) {
            select.innerHTML = '<option value="">-- Choose saved beneficiary --</option>' +
                list.map(b => {
                    const label = b.nickname ? escapeHtml(b.nickname) + ' ('+escapeHtml(b.name)+')' : escapeHtml(b.name);
                    return `<option value="${escapeHtml(b.email)}">${label} — ${escapeHtml(b.email)}</option>`;
                }).join('');
        }
        // attach handlers for quick transfer and delete
        container.querySelectorAll('.quick-transfer').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const email = btn.dataset.email;
                window.location.href = '/transfer';
                // store chosen email temporarily
                sessionStorage.setItem('quick_transfer_email', email);
            });
        });
        container.querySelectorAll('.delete-benef').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = btn.dataset.id;
                try {
                    const csrfEl3 = document.querySelector('input[name="_csrf_token"]');
                    const csrfVal3 = csrfEl3 ? csrfEl3.value : '';
                    await fetch(`/api/beneficiaries/${id}`, { method: 'DELETE', credentials: 'same-origin', headers: { "X-CSRFToken": csrfVal3 } });
                    setMessage(message, 'Beneficiary removed.', 'success');
                    await delay(300);
                    refresh();
                } catch (err) {
                    setMessage(message, 'Failed to remove beneficiary.', 'error');
                }
            });
        });
    };

    refresh();

    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        setMessage(message, '', '');
        const name = (document.getElementById('benef-name') || {}).value || '';
        const email = (document.getElementById('benef-email') || {}).value || '';
        const nickname = (document.getElementById('benef-nick') || {}).value || '';
        if (!name || !email) {
            setMessage(message, 'Name and email are required.', 'error');
            return;
        }
        try {
            const data = await apiRequest('/api/beneficiaries', { method: 'POST', body: JSON.stringify({ name, email, nickname }) });
            setMessage(message, data.message || 'Beneficiary added.', 'success');
            form.reset();
            await delay(400);
            refresh();
        } catch (err) {
            setMessage(message, err.message, 'error');
        }
    });
};


const setupChangePin = () => {
    const container = document.querySelector("[data-page='change-pin']");
    if (!container) return;

    const form = document.getElementById("change-pin-form");
    const message = document.getElementById("change-pin-message");
    const emailInput = document.getElementById("change-pin-email");
    const passwordInput = document.getElementById("change-pin-password");
    const newPinInput = document.getElementById("change-pin-new");
    const confirmPinInput = document.getElementById("change-pin-confirm");

    if (!form) return;

    const email = (container.dataset.email || emailInput?.value || "").trim();
    if (emailInput && email) {
        emailInput.value = email;
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        setMessage(message, "", "");

        const currentEmail = (emailInput ? emailInput.value : email).trim();
        const password = passwordInput ? passwordInput.value.trim() : "";
        const newPin = newPinInput ? newPinInput.value.trim() : "";
        const confirmPin = confirmPinInput ? confirmPinInput.value.trim() : "";

        if (!currentEmail || !password || !newPin || !confirmPin) {
            setMessage(message, "All fields are required.", "error");
            return;
        }
        if (newPin !== confirmPin) {
            setMessage(message, "New PIN entries do not match.", "error");
            return;
        }
        if (!/^\d{4}$/.test(newPin)) {
            setMessage(message, "PIN must be exactly 4 digits.", "error");
            return;
        }

        const button = form.querySelector("button[type='submit']");
        setButtonLoading(button, true, "Updating...");

        try {
            const data = await apiRequest("/api/change-pin", {
                method: "POST",
                body: JSON.stringify({
                    email: currentEmail,
                    password,
                    new_pin: newPin,
                }),
            });
            setMessage(message, data.message || "Your Transaction PIN has been updated.", "success");
            form.reset();
            if (emailInput && email) {
                emailInput.value = email;
            }
        } catch (error) {
            setMessage(message, error.message, "error");
        } finally {
            setButtonLoading(button, false);
        }
    });
};

const setupProfile = () => {
    const container = document.querySelector("[data-page='profile']");
    if (!container) return;

    const nameHeading = document.getElementById("userName");
    const emailHeading = document.getElementById("userEmail");
    const nameValue = document.getElementById("profile-name");
    const emailValue = document.getElementById("profile-email");
    const avatar = document.getElementById("profile-avatar");
    const editButton = document.getElementById("edit-profile");
    const modal = document.getElementById("edit-profile-modal");
    const editName = document.getElementById("edit-name");
    const editEmail = document.getElementById("edit-email");
    const editPin = document.getElementById("edit-pin");
    const saveButton = document.getElementById("save-profile");
    const closeButtons = modal ? modal.querySelectorAll("[data-close='modal']") : [];
    const message = document.getElementById("profile-message");
    const changePinForm = document.getElementById("change-pin-form");
    const currentPinInput = document.getElementById("current-pin");
    const newPinInput = document.getElementById("new-pin");
    const confirmPinInput = document.getElementById("confirm-pin");
    const pinMessage = document.getElementById("pin-message");

    const getInitials = (fullName) => {
        if (!fullName) return "SB";
        const parts = fullName.trim().split(/\s+/);
        const initials = parts.slice(0, 2).map((part) => part[0].toUpperCase());
        return initials.join("") || "SB";
    };

    const applyProfile = (data) => {
        if (nameHeading) nameHeading.textContent = data.name || "User";
        if (emailHeading) emailHeading.textContent = data.email || "";
        if (nameValue) nameValue.textContent = data.name || "-";
        if (emailValue) emailValue.textContent = data.email || "-";
        if (avatar) avatar.textContent = getInitials(data.name);
    };

    const openModal = () => {
        if (!modal) return;
        if (editName) editName.value = nameValue?.textContent || "";
        if (editEmail) editEmail.value = emailValue?.textContent || "";
        if (editPin) editPin.value = "";
        modal.classList.remove("hidden");
    };

    const closeModal = () => {
        if (!modal) return;
        modal.classList.add("hidden");
    };

    apiRequest("/api/profile")
        .then((data) => {
            applyProfile(data);
            // Load account details to populate account-specific profile fields
            const accountId = container.dataset.accountId || getAccountId();
            if (accountId) {
                apiRequest(`/api/account/${accountId}`)
                    .then((acct) => {
                        const acctTypeEl = document.getElementById("profile-account-type");
                        const memberSinceEl = document.getElementById("profile-member-since");
                        const acctLabel = acct.account_type_label || (acct.account_type ? acct.account_type.charAt(0).toUpperCase() + acct.account_type.slice(1) : "-");
                        if (acctTypeEl) acctTypeEl.textContent = acctLabel;
                        if (memberSinceEl) memberSinceEl.textContent = acct.created_at_display || (acct.created_at ? formatTimestamp(acct.created_at) : "-");
                    })
                    .catch((err) => {
                        console.warn("Failed to load account for profile:", err);
                    });
            } else {
                console.warn("No account id available for profile page.");
            }
        })
        .catch((error) => {
            setMessage(message, error.message, "error");
        });

    if (editButton) {
        editButton.addEventListener("click", openModal);
    }

    // load login activity
    const loginList = document.getElementById("login-activity-list");
    if (loginList) {
        apiRequest("/api/login-activity")
            .then((data) => {
                const items = data.logins || [];
                if (!items.length) {
                    loginList.innerHTML = "<li>No recent logins.</li>";
                    return;
                }
                loginList.innerHTML = items
                    .map((l) => `<li>${escapeHtml(l.created_at_display)} — ${escapeHtml(l.ip || '-')} <span class="muted">${escapeHtml(l.user_agent || '')}</span></li>`)
                    .join("");
            })
            .catch(() => {
                loginList.innerHTML = "<li>Unable to load login activity.</li>";
            });
    }

    if (closeButtons.length) {
        closeButtons.forEach((button) => {
            button.addEventListener("click", closeModal);
        });
    }

    if (saveButton) {
        saveButton.addEventListener("click", async () => {
            if (!editName || !editEmail) return;
            setMessage(message, "", "");
            setButtonLoading(saveButton, true, "Saving...");

            try {
                const data = await apiRequest("/api/profile/update", {
                    method: "POST",
                    body: JSON.stringify({
                        name: editName.value.trim(),
                        email: editEmail.value.trim(),
                        pin: editPin ? editPin.value.trim() : "",
                    }),
                });
                applyProfile(data);
                closeModal();
                setMessage(message, "Profile updated successfully.", "success");
            } catch (error) {
                setMessage(message, error.message, "error");
            } finally {
                setButtonLoading(saveButton, false);
            }
        });
    }

    if (changePinForm) {
        changePinForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            setMessage(pinMessage, "", "");

            const currentPin = currentPinInput ? currentPinInput.value.trim() : "";
            const newPin = newPinInput ? newPinInput.value.trim() : "";
            const confirmPin = confirmPinInput ? confirmPinInput.value.trim() : "";

            if (!currentPin || !newPin || !confirmPin) {
                setMessage(pinMessage, "All PIN fields are required.", "error");
                return;
            }
            if (newPin !== confirmPin) {
                setMessage(pinMessage, "New PIN entries do not match.", "error");
                return;
            }
            if (!/^\d{4}$/.test(newPin)) {
                setMessage(pinMessage, "PIN must be exactly 4 digits.", "error");
                return;
            }

            const button = changePinForm.querySelector("button[type='submit']");
            setButtonLoading(button, true, "Updating...");

            try {
                const data = await apiRequest("/api/update-pin", {
                    method: "POST",
                    body: JSON.stringify({
                        current_pin: currentPin,
                        new_pin: newPin,
                        confirm_pin: confirmPin,
                    }),
                });
                setMessage(pinMessage, data.message || "PIN updated successfully.", "success");
                if (currentPinInput) currentPinInput.value = "";
                if (newPinInput) newPinInput.value = "";
                if (confirmPinInput) confirmPinInput.value = "";
            } catch (error) {
                setMessage(pinMessage, error.message, "error");
            } finally {
                setButtonLoading(button, false);
            }
        });
    }
};

const setupSupportPage = () => {
    const container = document.querySelector("[data-page='support']");
    if (!container) return;

    const form = document.getElementById("support-form");
    const status = document.getElementById("support-status");
    const historyList = document.getElementById("support-history-list");

    const renderHistory = (queries) => {
        if (!historyList) return;
        if (!queries.length) {
            historyList.innerHTML = "<li>No queries yet.</li>";
            return;
        }
        historyList.innerHTML = queries
            .map((query) => {
                const dateLabel = query.created_at_display || formatTimestamp(query.created_at);
                const priority = query.priority || "Low";
                const priorityClass = priority.toLowerCase();
                return `
                    <li>
                        <a class="support-link" href="/support/${escapeHtml(query.id)}">
                            <div class="support-item">
                                <div>
                                    <strong>${escapeHtml(query.subject || "Support query")}</strong>
                                    <span class="meta">${escapeHtml(dateLabel)}</span>
                                </div>
                                <div class="support-tags">
                                    <span class="status-pill">${query.status || "Open"}</span>
                                    <span class="priority-pill ${priorityClass}">${priority}</span>
                                </div>
                            </div>
                        </a>
                    </li>
                `;
            })
            .join("");
    };

    const fetchHistory = () => {
        apiRequest("/api/support/history")
            .then((data) => {
                renderHistory(data.queries || []);
            })
            .catch((error) => {
                if (!historyList) return;
                historyList.innerHTML = `<li>${escapeHtml(error.message)}</li>`;
            });
    };

    fetchHistory();

    if (!form) return;

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        setMessage(status, "", "");

        const subject = form.subject.value.trim();
        const message = form.message.value.trim();
        const priority = form.priority.value;

        if (!subject || !message) {
            setMessage(status, "Subject and message are required.", "error");
            return;
        }

        const button = form.querySelector("button[type='submit']");
        setButtonLoading(button, true, "Submitting...");

        try {
            const data = await Promise.all([
                apiRequest("/api/support", {
                    method: "POST",
                    body: JSON.stringify({ subject, message, priority }),
                }),
                delay(450),
            ]).then(([result]) => result);
            setMessage(status, data.message || "Query submitted successfully.", "success");
            form.reset();
            fetchHistory();
        } catch (error) {
            setMessage(status, error.message, "error");
        } finally {
            setButtonLoading(button, false);
        }
    });
};

const setupAdminDashboard = () => {
    const container = document.querySelector("[data-page='admin']");
    if (!container) return;

    const usersCountEl = document.getElementById("admin-users-count");
    const accountsCountEl = document.getElementById("admin-accounts-count");
    const txCountEl = document.getElementById("admin-transactions-count");
    const openSupportEl = document.getElementById("admin-support-open");
    const usersList = document.getElementById("admin-users-list");
    const txList = document.getElementById("admin-transactions-list");
    const supportList = document.getElementById("admin-support-list");

    const renderUsers = (users) => {
        if (!usersList) return;
        usersList.innerHTML = users.length
            ? users.map((u) => `<li><strong>${escapeHtml(u.name || 'User')}</strong> <span class="meta">${escapeHtml(u.email || '')} · ${escapeHtml(u.role || 'user')} · ${escapeHtml(u.created_at_display || '')}</span></li>`).join("")
            : "<li>No users found.</li>";
    };

    const renderTransactions = (transactions) => {
        if (!txList) return;
        txList.innerHTML = transactions.length
            ? transactions.map((tx) => `<li><strong>${escapeHtml(tx.type || '-')}</strong> ${formatCurrency(tx.amount || 0)} <span class="meta">${escapeHtml(tx.created_at_display || '')}</span></li>`).join("")
            : "<li>No transactions found.</li>";
    };

    const renderSupport = (items) => {
        if (!supportList) return;
        if (!items.length) {
            supportList.innerHTML = "<div>No support items.</div>";
            return;
        }
        supportList.innerHTML = items.map((item) => `
            <div class="admin-support-item card">
                <div class="admin-support-meta">
                    <strong>${escapeHtml(item.subject || 'Support')}</strong>
                    <span class="meta">${escapeHtml(item.email || '')} · ${escapeHtml(item.priority || 'Low')} · ${escapeHtml(item.status || 'Open')} · ${escapeHtml(item.created_at_display || '')}</span>
                </div>
                <div class="admin-support-reply">
                    <textarea id="reply-${escapeHtml(item.id)}" rows="3" placeholder="Write a reply">${escapeHtml(item.admin_reply || '')}</textarea>
                    <button class="btn primary admin-reply-btn" data-query-id="${escapeHtml(item.id)}" type="button">Save Reply</button>
                </div>
            </div>
        `).join("");

        supportList.querySelectorAll(".admin-reply-btn").forEach((button) => {
            button.addEventListener("click", async () => {
                const queryId = button.dataset.queryId;
                const textarea = document.getElementById(`reply-${queryId}`);
                const reply = textarea ? textarea.value.trim() : "";
                if (!reply) return;
                try {
                    await apiRequest(`/api/admin/support/${queryId}/reply`, {
                        method: "POST",
                        body: JSON.stringify({ reply }),
                    });
                    fetchAdminData();
                } catch (error) {
                    console.error(error);
                }
            });
        });
    };

    const fetchAdminData = () => {
        Promise.all([
            apiRequest("/api/admin/overview"),
            apiRequest("/api/admin/users"),
            apiRequest("/api/admin/transactions"),
            apiRequest("/api/admin/support"),
        ])
            .then(([overview, users, transactions, support]) => {
                const totals = overview.totals || {};
                if (usersCountEl) usersCountEl.textContent = totals.users ?? 0;
                if (accountsCountEl) accountsCountEl.textContent = totals.accounts ?? 0;
                if (txCountEl) txCountEl.textContent = totals.transactions ?? 0;
                if (openSupportEl) openSupportEl.textContent = totals.support_open ?? 0;
                renderUsers(users.users || []);
                renderTransactions(transactions.transactions || []);
                renderSupport(support.support || []);
            })
            .catch((error) => {
                console.error("Failed to load admin dashboard:", error);
            });
    };

    fetchAdminData();
};

window.addEventListener("DOMContentLoaded", () => {
    const sidebarToggle = document.querySelector(".sidebar-toggle");
    if (sidebarToggle) {
        sidebarToggle.addEventListener("click", () => {
            document.body.classList.toggle("sidebar-open");
        });
    }

    document.body.addEventListener("click", (event) => {
        if (!document.body.classList.contains("sidebar-open")) return;
        const sidebar = document.querySelector(".sidebar");
        if (sidebar && sidebar.contains(event.target)) return;
        if (event.target.closest(".sidebar-toggle")) return;
        document.body.classList.remove("sidebar-open");
    });

    hydrateNavUser();
    setupCreateAccount();
    setupSignup();
    setupLogin();
    setupForgotPassword();
    setupResetPassword();
    setupLoginFlash();
    setupThemeToggle();
    setupAlertDismissals();
    setupTransact();
    setupDashboard();
    setupTransactions();

    setupProfile();
    setupBeneficiaries();
    setupTransferPage();
    setupSetPin();
    setupChangePin();
    setupChangePassword();
    setupSupportPage();
    setupAdminDashboard();
});
