const $ = (sel) => document.querySelector(sel);

async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok && res.status !== 502) {
    throw { status: res.status, data };
  }
  return data;
}

function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }
function markDone(stepEl) { stepEl.classList.add("done"); }

function log(pre, data) { pre.textContent = JSON.stringify(data, null, 2); }

// ---------------- status / dry run ----------------

async function refreshStatus() {
  const s = await api("GET", "/api/status");
  if (s.dry_run) show($("#dryRunPill")); else hide($("#dryRunPill"));
  if (s.logged_in) {
    $("#statusPill").textContent = "Logged in";
    $("#statusPill").className = "pill on";
    show($("#logoutBtn"));
    show($("#dashboard")); show($("#ltpSection")); show($("#ordersSection"));
    hide($("#loginSection"));
    $("#clientId").value = s.client_id || "";
  } else {
    $("#statusPill").textContent = "Not logged in";
    $("#statusPill").className = "pill off";
    hide($("#logoutBtn"));
    hide($("#dashboard")); hide($("#ltpSection")); hide($("#ordersSection"));
    show($("#loginSection"));
  }
  return s;
}

// ---------------- login wizard ----------------

$("#btnStart").addEventListener("click", async () => {
  const r = await api("POST", "/api/login/start");
  log($("#loginLog"), r);
  markDone($("#step1"));
  $("#btnUsername").disabled = false;
});

$("#btnUsername").addEventListener("click", async () => {
  const r = await api("POST", "/api/login/username", { username: $("#username").value });
  log($("#loginLog"), r);
  markDone($("#step2"));
  $("#btnOtp").disabled = false;
  $("#btnResendOtp").disabled = false;
});

$("#btnOtp").addEventListener("click", async () => {
  const r = await api("POST", "/api/login/otp", { otp: $("#otp").value });
  log($("#loginLog"), r);
  markDone($("#step3"));
  $("#btnPin").disabled = false;
  if (r.request_token) $("#requestToken").value = r.request_token;
});

$("#btnResendOtp").addEventListener("click", async () => {
  const r = await api("POST", "/api/login/otp/resend");
  log($("#loginLog"), r);
});

$("#btnPin").addEventListener("click", async () => {
  const r = await api("POST", "/api/login/pin", { answer: $("#pin").value });
  log($("#loginLog"), r);
  markDone($("#step4"));
  $("#btnAuthorise").disabled = false;
  if (r.request_token) $("#requestToken").value = r.request_token;
});

$("#btnAuthorise").addEventListener("click", async () => {
  const r = await api("POST", "/api/login/authorise", {
    request_token: $("#requestToken").value,
    consent: $("#consent").value,
  });
  log($("#loginLog"), r);
  markDone($("#step5"));
  $("#btnAccessToken").disabled = false;
  if (r.request_token) $("#requestToken").value = r.request_token;
});

$("#btnAccessToken").addEventListener("click", async () => {
  const r = await api("POST", "/api/login/access-token", { request_token: $("#requestToken").value });
  log($("#loginLog"), r);
  markDone($("#step6"));
  await refreshStatus();
});

$("#logoutBtn").addEventListener("click", async () => {
  await api("POST", "/api/logout");
  await refreshStatus();
});

// ---------------- LTP watchlist ----------------

let watchlist = [];
let pollTimer = null;

$("#btnAddLtp").addEventListener("click", () => {
  const exchange = $("#ltpExchange").value;
  const token = $("#ltpToken").value.trim();
  if (!token) return;
  watchlist.push({ exchange, token });
  renderLtpTable();
  $("#ltpToken").value = "";
});

function renderLtpTable(prices = {}) {
  const tbody = $("#ltpTable tbody");
  tbody.innerHTML = "";
  watchlist.forEach((row, i) => {
    const key = `${row.exchange}:${row.token}`;
    const p = prices[key];
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${row.exchange}</td><td>${row.token}</td>
      <td>${p ? p.ltp : "—"}</td><td>${p ? p.time : "—"}</td>
      <td><button class="secondary" data-remove="${i}">Remove</button></td>`;
    tbody.appendChild(tr);
  });
  tbody.querySelectorAll("[data-remove]").forEach((btn) => {
    btn.addEventListener("click", () => {
      watchlist.splice(Number(btn.dataset.remove), 1);
      renderLtpTable();
    });
  });
}

async function pollLtp() {
  if (watchlist.length === 0 || document.hidden) return;
  try {
    const r = await api("POST", "/api/ltp", { data: watchlist });
    const items = (r.raw && (r.raw.data || r.raw)) || [];
    const prices = {};
    const time = new Date().toLocaleTimeString();
    (Array.isArray(items) ? items : []).forEach((item) => {
      const exch = item.exchange || item.Exchange;
      const tok = item.token || item.Token || item.instrument_token;
      const ltp = item.ltp ?? item.LTP ?? item.last_price;
      if (exch && tok !== undefined) prices[`${exch}:${tok}`] = { ltp, time };
    });
    renderLtpTable(prices);
  } catch (e) {
    console.error("LTP poll failed", e);
  }
}

$("#btnTogglePoll").addEventListener("click", (e) => {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
    e.target.textContent = "Start polling";
  } else {
    pollLtp();
    pollTimer = setInterval(pollLtp, 5000);
    e.target.textContent = "Stop polling";
  }
});

// ---------------- Orders ----------------

document.querySelectorAll(".tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tabpanel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.querySelector(`.tabpanel[data-panel="${btn.dataset.tab}"]`).classList.add("active");
  });
});

function mountOrderForm(containerId) {
  const tpl = $("#orderFormTemplate");
  const container = document.getElementById(containerId);
  container.appendChild(tpl.content.cloneNode(true));
}
["regularPlaceForm", "regularModifyForm", "amoPlaceForm", "amoModifyForm",
 "coverPlaceForm", "coverModifyForm", "bracketPlaceForm", "bracketModifyForm"]
  .forEach(mountOrderForm);

function readOrderForm(containerId) {
  const container = document.getElementById(containerId);
  const get = (cls) => container.querySelector(`.${cls}`).value;
  return {
    exchange: get("f-exchange"),
    instrument_token: get("f-instrument_token"),
    order_side: get("f-order_side"),
    order_type: get("f-order_type"),
    price: Number(get("f-price")) || 0,
    trigger_price: Number(get("f-trigger_price")) || 0,
    quantity: Number(get("f-quantity")) || 0,
    disclosed_quantity: Number(get("f-disclosed_quantity")) || 0,
    product: get("f-product"),
    validity: get("f-validity"),
    user_order_id: Number(get("f-user_order_id")) || 0,
    device: get("f-device"),
    client_id: $("#clientId").value,
  };
}

async function placeOrder(kind, containerId) {
  const order = readOrderForm(containerId);
  const r = await api("POST", `/api/orders/${kind}`, order);
  log($("#orderLog"), r);
}

async function modifyOrder(kind, containerId, omsId, extra = {}) {
  const order = { ...readOrderForm(containerId), oms_order_id: omsId, ...extra };
  const r = await api("PUT", `/api/orders/${kind}`, order);
  log($("#orderLog"), r);
}

async function cancelOrder(kind, omsId, extraQuery = "") {
  const r = await api("DELETE", `/api/orders/${kind}/${omsId}${extraQuery}`);
  log($("#orderLog"), r);
}

async function cancelWithBody(kind, omsId, body) {
  const r = await api("DELETE", `/api/orders/${kind}/${omsId}`, body);
  log($("#orderLog"), r);
}

document.body.addEventListener("click", async (e) => {
  const action = e.target.dataset.action;
  if (!action) return;
  try {
    if (action === "place-regular") await placeOrder("regular", "regularPlaceForm");
    if (action === "modify-regular") await modifyOrder("regular", "regularModifyForm", $("#regularModifyOmsId").value);
    if (action === "cancel-regular") await cancelOrder("regular", $("#regularCancelOmsId").value,
      `?client_id=${encodeURIComponent($("#clientId").value)}`);

    if (action === "place-amo") await placeOrder("amo", "amoPlaceForm");
    if (action === "modify-amo") await modifyOrder("amo", "amoModifyForm", $("#amoModifyOmsId").value,
      { exchange_order_id: $("#amoModifyExchangeOrderId").value });
    if (action === "cancel-amo") await cancelOrder("amo", $("#amoCancelOmsId").value,
      `?client_id=${encodeURIComponent($("#clientId").value)}`);

    // place-cover and place-bracket have their own listeners below (they
    // need extra fields merged in), which stop this delegated handler
    // from also firing for those two buttons.
    if (action === "modify-cover") await modifyOrder("cover", "coverModifyForm", $("#coverModifyOmsId").value,
      { exchange_order_id: $("#coverModifyExchangeOrderId").value });
    if (action === "cancel-cover") await cancelWithBody("cover", $("#coverCancelOmsId").value, {
      client_id: $("#clientId").value,
      exchange_order_id: $("#coverCancelExchangeOrderId").value,
      leg_order_indicator: "ENTRY",
      oms_order_id: $("#coverCancelOmsId").value,
      status: "CONFIRMED",
    });

    if (action === "place-bracket") await placeOrder("bracket", "bracketPlaceForm");
    if (action === "modify-bracket") await modifyOrder("bracket", "bracketModifyForm", $("#bracketModifyOmsId").value,
      { exchange_order_id: $("#bracketModifyExchangeOrderId").value });
    if (action === "cancel-bracket") await cancelWithBody("bracket", $("#bracketCancelOmsId").value, {
      client_id: $("#clientId").value,
      exchange_order_id: $("#bracketCancelExchangeOrderId").value,
      leg_order_indicator: "ENTRY",
      oms_order_id: $("#bracketCancelOmsId").value,
      status: "CONFIRMED",
    });

    if (action === "place-gtt") {
      const gtt = {
        action_type: "single_order",
        expiry_time: $("#gttExpiry").value,
        order: {
          client_id: $("#clientId").value,
          device: "web",
          disclosed_quantity: 0,
          exchange: $("#gttExchange").value,
          instrument_token: $("#gttInstrumentToken").value,
          market_protection_percentage: 0,
          order_side: $("#gttOrderSide").value,
          order_type: $("#gttOrderType").value,
          price: Number($("#gttPrice").value) || 0,
          product: $("#gttProduct").value,
          quantity: Number($("#gttQuantity").value) || 0,
          sl_order_price: 0,
          sl_order_quantity: 0,
          sl_trigger_price: 0,
          trigger_price: Number($("#gttTriggerPrice").value) || 0,
          user_order_id: 10002,
        },
      };
      const r = await api("POST", "/api/orders/gtt", gtt);
      log($("#orderLog"), r);
    }
    if (action === "cancel-gtt") {
      const r = await api("DELETE", `/api/orders/gtt/${encodeURIComponent($("#clientId").value)}/${$("#gttCancelId").value}`);
      log($("#orderLog"), r);
    }
    if (action === "fetch-gtt") {
      const r = await api("GET", `/api/orders/gtt/${encodeURIComponent($("#clientId").value)}`);
      log($("#orderLog"), r);
    }
  } catch (err) {
    log($("#orderLog"), err.data || err);
  }
});

// Cover place needs stop_loss_value merged in — wire it explicitly (kept
// separate from the generic placeOrder() above since only Cover/Bracket
// have this field).
document.querySelector('[data-action="place-cover"]').addEventListener("click", async (e) => {
  e.stopImmediatePropagation();
  const order = { ...readOrderForm("coverPlaceForm"), stop_loss_value: Number($("#coverStopLoss").value) || 0, trailing_stop_loss: 0 };
  const r = await api("POST", "/api/orders/cover", order);
  log($("#orderLog"), r);
});
document.querySelector('[data-action="place-bracket"]').addEventListener("click", async (e) => {
  e.stopImmediatePropagation();
  const order = {
    ...readOrderForm("bracketPlaceForm"),
    square_off_value: Number($("#bracketSquareOff").value) || 0,
    stop_loss_value: Number($("#bracketStopLoss").value) || 0,
    trailing_stop_loss: $("#bracketTrailingSL").value,
    is_trailing: Number($("#bracketTrailingSL").value) > 0,
  };
  const r = await api("POST", "/api/orders/bracket", order);
  log($("#orderLog"), r);
});

refreshStatus();
