const state = {
  billId: null,
  page: 1,
  size: 20,
  pages: 1,
  sortBy: "trade_time",
  order: "desc",
  charts: {},
  direction: "",
  calYear: null,
  calMonth: null,
  calDirection: "支出",
  calSelectedDate: null,
  heatmapDirection: "支出",
  quickRange: "",
  budget: null,
  year: "",
  merchantName: "",
  markRow: null,
};

const $ = (id) => document.getElementById(id);

const fmtMoney = (v) =>
  "¥" + Number(v || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const fmtPct = (v) => `${Number(v || 0).toFixed(1)}%`;

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function showMsg(text, type = "") {
  const el = $("uploadMsg");
  el.className = "msg " + type;
  el.textContent = text || "";
}

function showBudgetMsg(text, type = "") {
  const el = $("budgetMsg");
  el.className = "msg " + type;
  el.textContent = text || "";
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  let payload = null;
  try {
    payload = await res.json();
  } catch (e) {
    payload = { success: false, message: `服务返回异常 (${res.status})` };
  }
  if (!res.ok || payload.success === false) {
    throw new Error(payload.message || `请求失败 (${res.status})`);
  }
  return payload.data;
}

function buildFilterQuery(extra = {}) {
  const params = new URLSearchParams();
  const add = (k, v) => {
    if (v !== undefined && v !== null && String(v).trim() !== "") params.append(k, v);
  };
  add("category", $("category").value);
  add("keyword", $("keyword").value);
  add("min_amount", $("minAmount").value);
  add("max_amount", $("maxAmount").value);
  add("weekday", $("weekday").value);
  if ($("excludeTransfer").checked) add("exclude_transfer", "1");
  if ($("excludeIgnored") && $("excludeIgnored").checked) add("exclude_ignored", "1");
  Object.entries(extra).forEach(([k, v]) => add(k, v));
  return params.toString();
}

function buildQuery(extra = {}) {
  const params = new URLSearchParams(buildFilterQuery());
  const add = (k, v) => {
    if (v !== undefined && v !== null && String(v).trim() !== "") params.append(k, v);
  };
  add("start_date", $("startDate").value);
  add("end_date", $("endDate").value);
  add("direction", $("direction").value);
  Object.entries(extra).forEach(([k, v]) => add(k, v));
  return params.toString();
}

/* ---------------- 上传 ---------------- */

function filesSelected() {
  return Array.from($("fileInput").files || []);
}

$("btnUpload").addEventListener("click", async () => {
  const files = filesSelected();
  if (!files.length) return showMsg("请先选择文件", "error");
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const pwd = $("zipPassword").value.trim();
  if (pwd) form.append("zip_password", pwd);
  showMsg(`正在上传解析 ${files.length} 个文件...`);
  $("btnUpload").disabled = true;
  try {
    const data = await api("/api/bills/upload", { method: "POST", body: form });
    showMsg(
      `解析成功：${data.record_count} 条记录（收入 ${data.income_count} / 支出 ${data.expense_count}），渠道：${data.channel}`,
      "ok"
    );
    await loadBillList();
    await selectBill(data.bill_id);
  } catch (e) {
    showMsg(e.message, "error");
  } finally {
    $("btnUpload").disabled = false;
  }
});

$("btnPreview").addEventListener("click", async () => {
  const files = filesSelected();
  if (!files.length) return showMsg("请先选择文件", "error");
  const file = files[0];
  const form = new FormData();
  form.append("file", file);
  showMsg("正在预览解析...");
  try {
    const data = await api("/api/bills/preview", { method: "POST", body: form });
    showMsg(
      `预览成功：识别到 ${data.row_count} 条记录，渠道 ${data.channel}，列：${data.columns.join(", ")}` +
        (data.warnings.length ? `；提示：${data.warnings.join("；")}` : ""),
      "ok"
    );
  } catch (e) {
    showMsg(e.message, "error");
  }
});

/* ---------------- 账单列表 ---------------- */

async function loadBillList() {
  const list = await api("/api/bills");
  const box = $("billList");
  if (!list.length) {
    box.innerHTML = '<div class="hint">暂无历史账单</div>';
    return;
  }
  box.innerHTML = list
    .map(
      (b) => `<div class="bill-item" data-id="${b.bill_id}">
        <span>${b.bill_id}</span>
        <span class="meta">${b.record_count} 条 · ${esc(b.channel)}</span>
      </div>`
    )
    .join("");
  box.querySelectorAll(".bill-item").forEach((el) =>
    el.addEventListener("click", () => selectBill(el.dataset.id))
  );
}

function markActive(billId) {
  document.querySelectorAll(".bill-item").forEach((el) =>
    el.classList.toggle("active", el.dataset.id === billId)
  );
}

async function selectBill(billId) {
  state.billId = billId;
  state.page = 1;
  state.calYear = null;
  state.calMonth = null;
  state.calSelectedDate = null;
  state.budget = null;
  markActive(billId);
  const info = await api(`/api/bills/${billId}`);
  $("status").textContent = `${info.source_file || billId} · ${info.record_count} 条 · ${info.start_date} ~ ${info.end_date}`;
  if (!state.calYear) {
    const months = await api(`/api/bills/${billId}/available-months`);
    if (months.length) {
      const last = months[months.length - 1];
      state.calYear = last.year;
      state.calMonth = last.month;
    }
  }
  await refreshAll();
  $("linkReport").href = `/report/${billId}?${buildQuery()}`;
}

/* ---------------- 数据刷新 ---------------- */

async function refreshAll() {
  if (!state.billId) return;
  const q = buildQuery();
  const activeDirection = $("direction").value || "支出";
  const [overview, trend, categories, counterparties, weekday, hours, heatmap, comparison, insights, budget,
    yearReport, catTrend, cumulative] =
    await Promise.all([
      api(`/api/bills/${state.billId}/overview?${q}`),
      api(`/api/bills/${state.billId}/trend?freq=month&${q}`),
      api(`/api/bills/${state.billId}/categories?direction=${encodeURIComponent(activeDirection)}&${q}`),
      api(`/api/bills/${state.billId}/counterparties?top=10&direction=${encodeURIComponent(activeDirection)}&${q}`),
      api(`/api/bills/${state.billId}/weekday?${q}`),
      api(`/api/bills/${state.billId}/hours?${q}`),
      api(`/api/bills/${state.billId}/heatmap?direction=${encodeURIComponent(state.heatmapDirection)}&${q}`),
      api(`/api/bills/${state.billId}/comparison?direction=${encodeURIComponent(activeDirection)}&${q}`),
      api(`/api/bills/${state.billId}/insights?${q}`),
      api(`/api/bills/${state.billId}/budget?${q}`),
      api(`/api/bills/${state.billId}/year-report?year=${encodeURIComponent(state.year || "")}&${q}`),
      api(`/api/bills/${state.billId}/category-trend?${q}`),
      api(`/api/bills/${state.billId}/cumulative?${q}`),
    ]);
  renderCards(overview);
  renderTrend(trend);
  renderCategory(categories);
  renderCounterparty(counterparties, activeDirection);
  renderWeekday(weekday, activeDirection);
  renderHour(hours, activeDirection);
  renderHeatmap(heatmap);
  renderComparison(comparison, activeDirection);
  renderInsights(insights);
  renderBudget(budget);
  renderYear(yearReport);
  renderCategoryTrend(catTrend);
  renderCumulative(cumulative);
  await loadCalendar();
  await loadMeta();
  await loadTransactions();
}

async function loadMeta() {
  const meta = await api("/api/meta");
  const sel = $("category");
  const current = sel.value;
  sel.innerHTML = '<option value="">全部</option>' +
    meta.categories.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
  sel.value = current;

  const bsel = $("budgetCategory");
  const bcur = bsel.value;
  bsel.innerHTML = '<option value="">选择分类</option>' +
    meta.categories.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
  bsel.value = bcur;
}

function renderCards(o) {
  const cards = [
    { label: "收入合计", value: fmtMoney(o.income_total), cls: "green", sub: `${o.income_count} 笔` },
    { label: "支出合计", value: fmtMoney(o.expense_total), cls: "red", sub: `${o.expense_count} 笔` },
    { label: "净收支", value: fmtMoney(o.net_total), cls: o.net_total >= 0 ? "green" : "red" },
    { label: "日均支出", value: fmtMoney(o.avg_daily_expense), sub: `${o.days} 天` },
    { label: "笔均支出", value: fmtMoney(o.avg_ticket) },
    { label: "最大单笔", value: fmtMoney(o.max_expense) },
    { label: "储蓄率", value: fmtPct(o.savings_rate), cls: (o.savings_rate || 0) >= 20 ? "green" : "" },
    { label: "本月预测支出", value: fmtMoney(o.forecast_month_expense), sub: "按日均推算" },
    { label: "转账/退款", value: `${o.transfer_count || 0} 笔`, sub: fmtMoney(o.transfer_amount) },
    { label: "记录总数", value: o.record_count },
    { label: "时间范围", value: `${o.start_date || "-"}`, sub: `至 ${o.end_date || "-"}` },
  ];
  $("cards").innerHTML = cards
    .map(
      (c) => `<div class="card">
        <div class="label">${c.label}</div>
        <div class="value ${c.cls || ""}">${c.value}</div>
        ${c.sub ? `<div class="sub">${c.sub}</div>` : ""}
      </div>`
    )
    .join("");
}

function makeChart(key, canvasId, config) {
  if (state.charts[key]) state.charts[key].destroy();
  const ctx = $(canvasId).getContext("2d");
  state.charts[key] = new Chart(ctx, config);
}

const PALETTE = ["#2b5fed", "#12b886", "#f2564b", "#f59f00", "#7048e8", "#15aabf",
  "#e64980", "#82c91e", "#fd7e14", "#4c6ef5", "#20c997", "#868e96"];

function applyFilter(mutator) {
  mutator();
  state.page = 1;
  markQuickRange("");
  refreshAll().catch((e) => showMsg(e.message, "error"));
}

function renderTrend(rows) {
  makeChart("trend", "chartTrend", {
    type: "line",
    data: {
      labels: rows.map((r) => r.period),
      datasets: [
        {
          label: "收入",
          data: rows.map((r) => r.income),
          borderColor: "#12b886",
          backgroundColor: "rgba(18,184,134,.12)",
          fill: true,
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: "#12b886",
        },
        {
          label: "支出",
          data: rows.map((r) => r.expense),
          borderColor: "#f2564b",
          backgroundColor: "rgba(242,86,75,.12)",
          fill: true,
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: "#f2564b",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      onClick: (evt, elements) => {
        if (!elements.length) return;
        const period = rows[elements[0].index].period;
        if (!/^\d{4}-\d{2}$/.test(String(period))) return;
        applyFilter(() => {
          $("startDate").value = `${period}-01`;
          $("endDate").value = `${period}-31`;
        });
      },
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: { label: (ctx) => `${ctx.dataset.label}: ${fmtMoney(ctx.parsed.y)}` },
        },
      },
      scales: { y: { beginAtZero: true } },
    },
  });
}

function renderCategory(rows) {
  makeChart("category", "chartCategory", {
    type: "doughnut",
    data: {
      labels: rows.map((r) => r.category),
      datasets: [{ data: rows.map((r) => r.amount), backgroundColor: PALETTE }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      onClick: (evt, elements) => {
        if (!elements.length) return;
        const name = rows[elements[0].index].category;
        applyFilter(() => ($("category").value = name));
      },
      plugins: { legend: { position: "right", labels: { boxWidth: 10, font: { size: 11 } } } },
    },
  });
}

function renderCounterparty(rows) {
  makeChart("counterparty", "chartCounterparty", {
    type: "bar",
    data: {
      labels: rows.map((r) => (r.counterparty || "(空)").slice(0, 12)),
      datasets: [{ label: "金额", data: rows.map((r) => r.amount), backgroundColor: "#2b5fed" }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      onClick: (evt, elements) => {
        if (!elements.length) return;
        const name = rows[elements[0].index].counterparty;
        if (name) openMerchant(name);
      },
      plugins: { legend: { display: false } },
    },
  });
}

function renderWeekday(rows, direction) {
  makeChart("weekday", "chartWeekday", {
    type: "bar",
    data: {
      labels: rows.map((r) => r.weekday),
      datasets: [{ label: `${direction}金额`, data: rows.map((r) => r.amount), backgroundColor: "#7048e8" }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      onClick: (evt, elements) => {
        if (!elements.length) return;
        const idx = elements[0].index + 1;
        applyFilter(() => ($("weekday").value = String(idx)));
      },
      plugins: { legend: { display: false } },
    },
  });
}

function renderHour(rows, direction) {
  makeChart("hour", "chartHour", {
    type: "bar",
    data: {
      labels: rows.map((r) => `${r.hour}时`),
      datasets: [{ label: `${direction}金额`, data: rows.map((r) => r.amount), backgroundColor: "#15aabf" }],
    },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
  });
}

/* ---------------- 年度概览 / 分类趋势 / 累计支出 ---------------- */

function renderYear(data) {
  const years = data.available_years || [];
  const sel = $("yearSelect");
  const current = data.year || "";
  sel.innerHTML = years.length
    ? years.map((y) => `<option value="${esc(y)}">${esc(y)} 年</option>`).join("")
    : '<option value="">--</option>';
  sel.value = current;

  const maxMonth = Math.max(...(data.months || []).map((m) => m.expense), 0);
  $("yearMonths").innerHTML = (data.months || [])
    .map((m) => {
      const level = maxMonth ? Math.min(4, Math.floor((m.expense / maxMonth) * 4.999)) : 0;
      const bg = ["#eef1f6", "#c7d8ff", "#8fb4ff", "#5b8df5", "#2b5fed"][level];
      const color = level >= 2 ? "#fff" : "#22293a";
      return `<div class="month-cell" data-month="${m.month_key}" style="background:${bg};color:${color}">
        <div class="m">${Number(m.month)}月</div>
        <div>${m.expense > 0 ? "¥" + Math.round(m.expense).toLocaleString("zh-CN") : "-"}</div>
        <div style="opacity:.75">${m.count}笔</div>
      </div>`;
    })
    .join("");

  $("yearMonths").querySelectorAll(".month-cell").forEach((el) =>
    el.addEventListener("click", () => {
      const key = el.dataset.month;
      if (!key) return;
      applyFilter(() => {
        $("startDate").value = `${key}-01`;
        $("endDate").value = `${key}-31`;
      });
    })
  );

  $("yearHint").textContent = current
    ? `${current} 年 · 支出 ¥${Number(data.expense_total || 0).toLocaleString("zh-CN")}`
    : "无数据";

  $("yearKpis").innerHTML = `
    <div class="item"><span class="label">年支出</span><span class="val red">${fmtMoney(data.expense_total)}</span></div>
    <div class="item"><span class="label">年收入</span><span class="val green">${fmtMoney(data.income_total)}</span></div>
    <div class="item"><span class="label">净结余</span><span class="val ${data.net_total >= 0 ? "green" : "red"}">${fmtMoney(data.net_total)}</span></div>
    <div class="item"><span class="label">储蓄率</span><span class="val">${fmtPct(data.savings_rate)}</span></div>
    <div class="item"><span class="label">月均支出</span><span class="val">${fmtMoney(data.avg_month_expense)}</span></div>
    <div class="item"><span class="label">活跃天数</span><span class="val">${data.active_days || 0}</span></div>
    <div class="item"><span class="label">最大单笔</span><span class="val">${fmtMoney(data.max_expense)}</span></div>
    <div class="item"><span class="label">最大单笔商户</span><span class="val" style="font-size:13px">${esc(data.max_expense_name || "-")}</span></div>
  `;
}

function renderCategoryTrend(data) {
  const months = data.months || [];
  makeChart("catTrend", "chartCatTrend", {
    type: "bar",
    data: {
      labels: months,
      datasets: (data.series || []).map((s, i) => ({
        label: s.category,
        data: s.data,
        backgroundColor: PALETTE[i % PALETTE.length],
        stack: "cat",
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 10 } } },
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${fmtMoney(ctx.parsed.y)}` } },
      },
      scales: {
        x: { stacked: true, ticks: { font: { size: 10 } } },
        y: { stacked: true, beginAtZero: true, ticks: { font: { size: 10 } } },
      },
    },
  });
}

function renderCumulative(data) {
  const rows = data.rows || [];
  makeChart("cumulative", "chartCumulative", {
    type: "line",
    data: {
      labels: rows.map((r) => String(r.date).slice(5)),
      datasets: [
        {
          label: "累计支出",
          data: rows.map((r) => r.cumulative),
          borderColor: "#f2564b",
          backgroundColor: "rgba(242,86,75,.10)",
          fill: true,
          tension: 0.25,
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => `累计 ${fmtMoney(ctx.parsed.y)}` } },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 10, font: { size: 10 } } },
        y: { beginAtZero: true, ticks: { font: { size: 10 } } },
      },
    },
  });
}

/* ---------------- 商户画像 ---------------- */

async function openMerchant(name) {
  if (!state.billId || !name) return;
  state.merchantName = name;
  $("merchantTitle").textContent = `商户画像 · ${name}`;
  $("merchantBody").innerHTML = '<div class="hint">加载中...</div>';
  openDrawer(true);
  try {
    const data = await api(
      `/api/bills/${state.billId}/merchant?name=${encodeURIComponent(name)}&${buildQuery()}`
    );
    const maxHour = Math.max(...(data.by_hour || []).map((h) => h.amount), 1);
    const maxCat = Math.max(...(data.by_category || []).map((c) => c.amount), 1);
    $("merchantTitle").textContent = `商户画像 · ${data.name}`;
    $("merchantBody").innerHTML = `
      <div class="profile-kpis">
        <div class="kpi"><div class="k">笔数</div><div class="v">${data.count}</div></div>
        <div class="kpi"><div class="k">累计</div><div class="v">${fmtMoney(data.total)}</div></div>
        <div class="kpi"><div class="k">笔均</div><div class="v">${fmtMoney(data.avg)}</div></div>
        <div class="kpi"><div class="k">最大单笔</div><div class="v">${fmtMoney(data.max)}</div></div>
        <div class="kpi"><div class="k">活跃月数</div><div class="v">${data.active_months}</div></div>
        <div class="kpi"><div class="k">平均间隔</div><div class="v">${data.avg_interval_days} 天</div></div>
      </div>
      <div class="profile-block">
        <h4>首末交易</h4>
        <div class="hint">${esc(String(data.first || "").slice(0, 16))} ~ ${esc(String(data.last || "").slice(0, 16))}</div>
      </div>
      <div class="profile-block">
        <h4>消费时段分布</h4>
        ${(data.by_hour || [])
          .map(
            (h) => `<div class="profile-row">
              <span>${h.hour} 时</span>
              <span class="track"><i class="fill" style="width:${(h.amount / maxHour) * 100}%"></i></span>
              <span>${fmtMoney(h.amount)}</span>
            </div>`
          )
          .join("")}
      </div>
      <div class="profile-block">
        <h4>分类构成</h4>
        ${(data.by_category || [])
          .map(
            (c) => `<div class="profile-row">
              <span>${esc(c.category)}</span>
              <span class="track"><i class="fill" style="width:${(c.amount / maxCat) * 100}%"></i></span>
              <span>${fmtMoney(c.amount)}</span>
            </div>`
          )
          .join("")}
      </div>
      <div class="profile-block">
        <h4>按月消费</h4>
        <table>
          <thead><tr><th>月份</th><th>笔数</th><th>金额</th></tr></thead>
          <tbody>
          ${(data.by_month || [])
            .map((m) => `<tr><td>${esc(m.month)}</td><td>${m.count}</td><td>${fmtMoney(m.amount)}</td></tr>`)
            .join("")}
          </tbody>
        </table>
      </div>
      <div class="profile-block">
        <h4>常见商品</h4>
        <table>
          <thead><tr><th>商品</th><th>笔数</th><th>金额</th></tr></thead>
          <tbody>
          ${(data.top_goods || [])
            .map((g) => `<tr><td>${esc(String(g.goods).slice(0, 20))}</td><td>${g.count}</td><td>${fmtMoney(g.amount)}</td></tr>`)
            .join("")}
          </tbody>
        </table>
      </div>
    `;
  } catch (e) {
    $("merchantBody").innerHTML = `<div class="msg error">${esc(e.message)}</div>`;
  }
}

function openDrawer(show) {
  $("merchantDrawer").classList.toggle("show", show);
  $("drawerMask").classList.toggle("show", show);
}

$("merchantClose").addEventListener("click", () => openDrawer(false));
$("drawerMask").addEventListener("click", () => openDrawer(false));
$("merchantFilter").addEventListener("click", () => {
  const name = state.merchantName;
  openDrawer(false);
  if (name) applyFilter(() => ($("keyword").value = name));
});

/* ---------------- 7x24 热力图 ---------------- */

function heatLevel(v, max) {
  if (!v || v <= 0) return 0;
  if (!max) return 1;
  const r = v / max;
  if (r >= 0.75) return 4;
  if (r >= 0.5) return 3;
  if (r >= 0.25) return 2;
  return 1;
}

function renderHeatmap(data) {
  const hoursEl = $("heatmapHours");
  const gridEl = $("heatmapGrid");
  const hours = data.hours || Array.from({ length: 24 }, (_, i) => i);
  hoursEl.innerHTML = `<span class="head"></span>` +
    hours.map((h) => `<span>${h}</span>`).join("");

  const max = data.max_amount || 0;
  const cells = [];
  (data.weekdays || []).forEach((label, wd) => {
    cells.push(`<div class="heatmap-row-label">${esc(label)}</div>`);
    hours.forEach((h) => {
      const amount = (data.matrix?.[wd]?.[h]) || 0;
      const count = (data.counts?.[wd]?.[h]) || 0;
      const lv = heatLevel(amount, max);
      const cls = `hm-cell l${lv}${amount > 0 ? " has-data" : ""}`;
      const tip = `${label} ${h}:00-${h}:59\n金额 ${fmtMoney(amount)} · ${count} 笔`;
      cells.push(`<div class="${cls}" title="${tip.replace(/"/g, "&quot;")}"></div>`);
    });
  });
  gridEl.innerHTML = cells.join("");
  $("heatmapHint").textContent =
    data.total > 0 ? `合计 ${fmtMoney(data.total)} · 峰值 ${fmtMoney(max)}` : "当前条件下无数据";
}

/* ---------------- 环比 ---------------- */

function renderComparison(data, direction) {
  const cur = data.current || {};
  const prev = data.previous || {};
  const yoy = data.yoy || {};
  const delta = data.delta || {};
  const pct = Number(delta.amount_pct || 0);
  const cls = pct > 0 ? "up" : pct < 0 ? "down" : "flat";
  const arrow = pct > 0 ? "▲" : pct < 0 ? "▼" : "—";

  $("compareHint").textContent = prev.month
    ? `${prev.month} → ${cur.month}（${direction}）`
    : "数据不足，无法对比";

  $("compareStats").innerHTML = `
    <div class="compare-stat">
      <div class="label">${esc(cur.month || "-")} ${esc(direction)}</div>
      <div class="val">${fmtMoney(cur.amount)}</div>
      <div class="delta ${cls}">${arrow} ${Math.abs(pct).toFixed(1)}% （${fmtMoney(Math.abs(delta.amount || 0))}）</div>
    </div>
    <div class="compare-stat">
      <div class="label">${esc(prev.month || "-")} ${esc(direction)}</div>
      <div class="val">${fmtMoney(prev.amount)}</div>
      <div class="delta flat">${prev.count || 0} 笔</div>
    </div>
    <div class="compare-stat">
      <div class="label">笔数变化</div>
      <div class="val">${delta.count > 0 ? "+" : ""}${delta.count || 0}</div>
      <div class="delta flat">当前 ${cur.count || 0} 笔</div>
    </div>
    <div class="compare-stat">
      <div class="label">同比（${esc(yoy.month || "-")}）</div>
      <div class="val">${fmtMoney(yoy.amount)}</div>
      <div class="delta ${yoy.amount_pct > 0 ? "up" : yoy.amount_pct < 0 ? "down" : "flat"}">
        ${yoy.amount ? `${yoy.amount_pct > 0 ? "▲" : yoy.amount_pct < 0 ? "▼" : "—"} ${Math.abs(yoy.amount_pct).toFixed(1)}%` : "无同期数据"}
      </div>
    </div>
  `;

  const cats = (data.categories || []).slice(0, 7);
  makeChart("compare", "chartCompare", {
    type: "bar",
    data: {
      labels: cats.map((c) => c.category),
      datasets: [
        { label: prev.month || "上月", data: cats.map((c) => c.previous), backgroundColor: "#c7d8ff" },
        { label: cur.month || "本月", data: cats.map((c) => c.current), backgroundColor: "#2b5fed" },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 10 } } },
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${fmtMoney(ctx.parsed.x)}` } },
      },
      scales: {
        x: { beginAtZero: true, ticks: { font: { size: 10 } } },
        y: { ticks: { font: { size: 10 } } },
      },
    },
  });
}

/* ---------------- 洞察 ---------------- */

function renderInsights(list) {
  if (!list || !list.length) {
    $("insightList").innerHTML = '<div class="hint">当前条件下暂无洞察</div>';
    return;
  }
  $("insightList").innerHTML = list
    .map(
      (i) => `<div class="insight-card ${esc(i.level || "")}">
        <div class="tag">${esc(i.type || "")}</div>
        <div class="title">${esc(i.title || "")}</div>
        <div class="detail">${esc(i.detail || "")}</div>
      </div>`
    )
    .join("");
}

/* ---------------- 预算 ---------------- */

function renderBudget(data) {
  state.budget = data;
  const monthly = Number(data.monthly || 0);
  const used = Number(data.used || 0);
  const percent = Number(data.percent || 0);
  const ring = $("budgetRing");

  $("budgetMonthHint").textContent = data.month ? `${data.month} 执行情况` : "暂无支出月份";
  ring.classList.toggle("over", !!data.over);
  const deg = Math.min(percent, 100) * 3.6;
  const color = data.over ? "#f2564b" : "#2b5fed";
  ring.style.background = `conic-gradient(${color} ${deg}deg, #e3e8f2 ${deg}deg)`;
  $("budgetRingText").textContent = monthly > 0 ? fmtPct(percent) : "--";
  $("budgetRingCaption").textContent =
    monthly > 0
      ? `已用 ${fmtMoney(used)} / 预算 ${fmtMoney(monthly)}`
      : "未设置预算";

  const items = [];
  if (monthly > 0) {
    items.push(`<div class="budget-item ${data.over ? "over" : ""}">
      <div class="top"><span>总预算</span><span>${fmtMoney(used)} / ${fmtMoney(monthly)}（${fmtPct(percent)}）</span></div>
      <div class="bar"><i style="width:${Math.min(percent, 100)}%"></i></div>
    </div>`);
    items.push(`<div class="hint">${data.over ? `已超支 ${fmtMoney(Math.abs(data.remaining))}` : `剩余 ${fmtMoney(data.remaining)}`}</div>`);
  }
  (data.categories || []).forEach((c) => {
    items.push(`<div class="budget-item ${c.percent > 100 ? "over" : ""}">
      <div class="top"><span>${esc(c.category)}</span><span>${fmtMoney(c.used)} / ${fmtMoney(c.budget)}（${fmtPct(c.percent)}）</span></div>
      <div class="bar"><i style="width:${Math.min(c.percent, 100)}%"></i></div>
    </div>`);
  });
  $("budgetDetail").innerHTML = items.join("") || '<div class="hint">设置月预算后可见执行进度</div>';
  $("budgetMonthly").value = monthly || "";
}

$("btnBudgetSave").addEventListener("click", async () => {
  if (!state.billId) return showBudgetMsg("请先加载账单", "error");
  const monthly = Number($("budgetMonthly").value || 0);
  const cat = $("budgetCategory").value;
  const amount = Number($("budgetAmount").value || 0);
  const categories = {};
  (state.budget?.categories || []).forEach((c) => {
    categories[c.category] = c.budget;
  });
  if (cat && amount > 0) categories[cat] = amount;
  showBudgetMsg("正在保存...");
  try {
    await api(`/api/bills/${state.billId}/budget`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ monthly, categories }),
    });
    $("budgetAmount").value = "";
    showBudgetMsg("预算已保存", "ok");
    const data = await api(`/api/bills/${state.billId}/budget?${buildQuery()}`);
    renderBudget(data);
  } catch (e) {
    showBudgetMsg(e.message, "error");
  }
});

$("btnBudgetClear").addEventListener("click", async () => {
  if (!state.billId) return showBudgetMsg("请先加载账单", "error");
  const monthly = Number($("budgetMonthly").value || 0);
  try {
    await api(`/api/bills/${state.billId}/budget`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ monthly, categories: {} }),
    });
    showBudgetMsg("分类预算已清空", "ok");
    const data = await api(`/api/bills/${state.billId}/budget?${buildQuery()}`);
    renderBudget(data);
  } catch (e) {
    showBudgetMsg(e.message, "error");
  }
});

/* ---------------- 自然语言查询 ---------------- */

async function runNlQuery() {
  if (!state.billId) return;
  const q = $("nlInput").value.trim();
  if (!q) {
    $("nlResult").innerHTML = '<div class="hint">请输入查询内容</div>';
    return;
  }
  $("btnNlQuery").disabled = true;
  $("nlResult").innerHTML = '<div class="hint">正在解析...</div>';
  try {
    const data = await api(`/api/bills/${state.billId}/nl-query?q=${encodeURIComponent(q)}&${buildQuery()}`);
    const p = data.parsed || {};
    const tags = [];
    if (p.start_date) tags.push(`${p.start_date} ~ ${p.end_date}`);
    if (p.direction) tags.push(p.direction);
    if (p.category) tags.push(`分类：${p.category}`);
    if (p.keyword) tags.push(`关键词：${p.keyword}`);
    if (p.min_amount) tags.push(`≥ ${p.min_amount}`);
    if (p.max_amount) tags.push(`≤ ${p.max_amount}`);
    const rows = data.rows || [];
    $("nlResult").innerHTML = `
      <div class="nl-answer">${esc(data.answer)}</div>
      <div class="nl-tags">${tags.map((t) => `<span class="nl-tag">${esc(t)}</span>`).join("") || '<span class="nl-tag">未识别到额外条件</span>'}</div>
      <div class="nl-list">
        ${rows
          .map(
            (r) => `<div class="nl-item">
              <span>${esc(String(r.trade_time || "").slice(0, 16))}</span>
              <span>${esc(r.direction || "")}</span>
              <span class="amt ${r.direction === "收入" ? "income" : "expense"}">${fmtMoney(r.amount)}</span>
              <span>${esc(r.counterparty || "")} · ${esc(r.category || "")}</span>
            </div>`
          )
          .join("") || '<div class="hint">无匹配记录</div>'}
      </div>
    `;
  } catch (e) {
    $("nlResult").innerHTML = `<div class="msg error">${esc(e.message)}</div>`;
  } finally {
    $("btnNlQuery").disabled = false;
  }
}

$("btnNlQuery").addEventListener("click", runNlQuery);
$("nlInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") runNlQuery();
});

/* ---------------- 快捷日期 ---------------- */

function fmtDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function markQuickRange(key) {
  state.quickRange = key;
  document.querySelectorAll(".quick-range .chip").forEach((el) =>
    el.classList.toggle("active", el.dataset.range === key)
  );
}

document.querySelectorAll(".quick-range .chip").forEach((btn) =>
  btn.addEventListener("click", () => {
    const key = btn.dataset.range;
    const now = new Date();
    let start = "";
    let end = fmtDate(now);
    if (key === "today") {
      start = end;
    } else if (key === "week") {
      const day = now.getDay() || 7;
      const monday = new Date(now);
      monday.setDate(now.getDate() - day + 1);
      start = fmtDate(monday);
    } else if (key === "month") {
      start = fmtDate(new Date(now.getFullYear(), now.getMonth(), 1));
    } else if (key === "lastmonth") {
      start = fmtDate(new Date(now.getFullYear(), now.getMonth() - 1, 1));
      end = fmtDate(new Date(now.getFullYear(), now.getMonth(), 0));
    } else if (key === "year") {
      start = fmtDate(new Date(now.getFullYear(), 0, 1));
    } else if (key === "days180") {
      const from = new Date(now);
      from.setDate(now.getDate() - 179);
      start = fmtDate(from);
    }
    $("startDate").value = start;
    $("endDate").value = end;
    markQuickRange(key);
    state.page = 1;
    refreshAll().catch((e) => showMsg(e.message, "error"));
  })
);

/* ---------------- 日历热力图 ---------------- */

async function loadCalendar() {
  if (!state.billId || !state.calYear || !state.calMonth) return;
  const ym = `year=${state.calYear}&month=${state.calMonth}&direction=${encodeURIComponent(state.calDirection)}&${buildFilterQuery()}`;
  const data = await api(`/api/bills/${state.billId}/calendar?${ym}`);
  renderCalendar(data);
}

function renderCalendar(data) {
  const grid = $("calendarGrid");
  const title = $("calTitle");
  const summary = $("calSummary");
  const y = state.calYear;
  const m = String(state.calMonth).padStart(2, "0");
  title.textContent = `${y}年${m}月`;

  const s = data.month_summary || {};
  const dirLabel = state.calDirection;
  const valCls = dirLabel === "支出" ? "red" : "green";
  summary.innerHTML = `
    <div class="item"><span>${dirLabel}合计</span><span class="val ${valCls}">${fmtMoney(s.total_expense || 0)}</span></div>
    <div class="item"><span>笔数</span><span class="val">${s.total_count || 0}</span></div>
    <div class="item"><span>消费天数</span><span class="val">${s.active_days || 0} / ${s.days_in_month || 30}</span></div>
    <div class="item"><span>日均${dirLabel}</span><span class="val">${fmtMoney(s.avg_expense || 0)}</span></div>
    <div class="item"><span>单日峰值</span><span class="val ${valCls}">${fmtMoney(s.max_expense || 0)}</span></div>
    <div class="item"><span>峰值日期</span><span class="val">${s.max_date || "-"}</span></div>
  `;

  if (!data.cells || !data.cells.length) {
    grid.innerHTML = '<div class="hint">该月无数据</div>';
    return;
  }

  grid.innerHTML = data.cells
    .map((c) => {
      const cls = c.in_month ? `cal-cell l${c.level}` : "cal-cell outside";
      const sel = state.calSelectedDate === c.date ? " selected" : "";
      const amtText = c.expense > 0 ? `¥${c.expense}` : "";
      const tip = c.in_month
        ? `${c.date}（周${c.weekday}）\n${state.calDirection}: ${fmtMoney(c.expense)} (${c.count}笔)` +
          (c.income > 0 ? `\n收入: ${fmtMoney(c.income)}` : "")
        : "";
      return `<div class="${cls}${sel}" data-date="${c.date}" data-in="${c.in_month}">
        <span class="day-num">${c.day}</span>
        ${amtText ? `<span class="day-amt">${amtText}</span>` : ""}
        <div class="cal-tooltip">${tip.replace(/\n/g, "<br>")}</div>
      </div>`;
    })
    .join("");

  grid.querySelectorAll(".cal-cell").forEach((el) =>
    el.addEventListener("click", () => {
      if (el.dataset.in !== "true") return;
      const d = el.dataset.date;
      if (state.calSelectedDate === d) {
        state.calSelectedDate = null;
        $("startDate").value = "";
        $("endDate").value = "";
      } else {
        state.calSelectedDate = d;
        $("startDate").value = d;
        $("endDate").value = d;
      }
      state.page = 1;
      markQuickRange("");
      renderCalendar(data);
      refreshAll().catch((e) => showMsg(e.message, "error"));
    })
  );
}

$("calPrev").addEventListener("click", async () => {
  if (!state.calYear) return;
  state.calMonth -= 1;
  if (state.calMonth < 1) {
    state.calMonth = 12;
    state.calYear -= 1;
  }
  state.calSelectedDate = null;
  await loadCalendar();
});

$("calNext").addEventListener("click", async () => {
  if (!state.calYear) return;
  state.calMonth += 1;
  if (state.calMonth > 12) {
    state.calMonth = 1;
    state.calYear += 1;
  }
  state.calSelectedDate = null;
  await loadCalendar();
});

$("calDirection").addEventListener("change", async () => {
  state.calDirection = $("calDirection").value;
  state.calSelectedDate = null;
  await loadCalendar();
});

$("heatmapDirection").addEventListener("change", async () => {
  state.heatmapDirection = $("heatmapDirection").value;
  if (!state.billId) return;
  try {
    const data = await api(
      `/api/bills/${state.billId}/heatmap?direction=${encodeURIComponent(state.heatmapDirection)}&${buildQuery()}`
    );
    renderHeatmap(data);
  } catch (e) {
    showMsg(e.message, "error");
  }
});

/* ---------------- 明细表 ---------------- */

async function loadTransactions() {
  if (!state.billId) return;
  const q = buildQuery({ page: state.page, size: state.size, sort_by: state.sortBy, order: state.order });
  const data = await api(`/api/bills/${state.billId}/transactions?${q}`);
  state.pages = data.pages || 1;
  $("pageInfo").textContent = `${data.page} / ${state.pages}（共 ${data.total} 条）`;
  $("btnPrev").disabled = data.page <= 1;
  $("btnNext").disabled = data.page >= state.pages;
  const tbody = $("txTable").querySelector("tbody");
  state.txRows = data.rows;
  if (!data.rows.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty">暂无数据</td></tr>';
    return;
  }
  tbody.innerHTML = data.rows
    .map((r) => {
      const cls = r.direction === "收入" ? "amount-income" : "amount-expense";
      const sign = r.direction === "收入" ? "+" : "-";
      const flag = r.is_transfer ? ' <span class="tag-pill">转账</span>' : "";
      const marks = [];
      if (r.tag) marks.push(`<span class="tag-pill">${esc(r.tag)}</span>`);
      if (r.ignored) marks.push('<span class="tag-pill" style="background:#feeceb;color:#d63b30">已忽略</span>');
      const btn = `<button class="mark-btn" data-key="${esc(r.row_key)}">${marks.length ? "编辑" : "标记"}</button>`;
      return `<tr class="${r.ignored ? "ignored-row" : ""}">
        <td>${esc(r.trade_time)}</td>
        <td>${esc(r.direction)}</td>
        <td class="${cls}">${sign}${fmtMoney(r.amount).slice(1)}</td>
        <td>${esc(r.category)}${flag}</td>
        <td>${esc(r.counterparty)}</td>
        <td>${esc(r.goods)}</td>
        <td>${esc(r.pay_method)}</td>
        <td>${esc(r.status)}</td>
        <td>${marks.join("")}${btn}</td>
      </tr>`;
    })
    .join("");
}

$("txTable").querySelector("tbody").addEventListener("click", (e) => {
  const btn = e.target.closest(".mark-btn");
  if (!btn) return;
  const row = (state.txRows || []).find((r) => r.row_key === btn.dataset.key);
  if (row) openMarkDialog(row);
});

/* ---------------- 交易标注 ---------------- */

function openMarkDialog(row) {
  state.markRow = row;
  $("markMeta").textContent = `${row.trade_time} · ${row.counterparty || "-"} · ${fmtMoney(row.amount)}`;
  $("markTag").value = row.tag || "";
  $("markNote").value = row.note || "";
  $("markIgnored").checked = !!row.ignored;
  $("markDialog").classList.add("show");
}

function closeMarkDialog() {
  $("markDialog").classList.remove("show");
  state.markRow = null;
}

async function saveMark() {
  const row = state.markRow;
  if (!row || !state.billId) return;
  try {
    await api(`/api/bills/${state.billId}/annotations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        key: row.row_key,
        tag: $("markTag").value,
        note: $("markNote").value,
        ignored: $("markIgnored").checked,
      }),
    });
    closeMarkDialog();
    await loadTransactions();
    if ($("excludeIgnored").checked) await refreshAll();
  } catch (e) {
    showMsg(e.message, "error");
  }
}

async function deleteMark() {
  const row = state.markRow;
  if (!row || !state.billId) return;
  try {
    await api(`/api/bills/${state.billId}/annotations`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: row.row_key }),
    });
    closeMarkDialog();
    await loadTransactions();
    if ($("excludeIgnored").checked) await refreshAll();
  } catch (e) {
    showMsg(e.message, "error");
  }
}

$("markSave").addEventListener("click", saveMark);
$("markDelete").addEventListener("click", deleteMark);
$("markCancel").addEventListener("click", closeMarkDialog);

$("btnPrev").addEventListener("click", () => {
  if (state.page > 1) {
    state.page -= 1;
    loadTransactions();
  }
});

$("btnNext").addEventListener("click", () => {
  if (state.page < state.pages) {
    state.page += 1;
    loadTransactions();
  }
});

document.querySelectorAll("#txTable th[data-sort]").forEach((th) =>
  th.addEventListener("click", () => {
    const key = th.dataset.sort;
    if (state.sortBy === key) {
      state.order = state.order === "asc" ? "desc" : "asc";
    } else {
      state.sortBy = key;
      state.order = "desc";
    }
    state.page = 1;
    loadTransactions();
  })
);

/* ---------------- 全局搜索 / 备份恢复 / 索引 ---------------- */

let searchTimer = null;

$("globalSearch").addEventListener("input", () => {
  clearTimeout(searchTimer);
  const q = $("globalSearch").value.trim();
  const panel = $("searchPanel");
  if (!q) {
    panel.classList.remove("show");
    panel.innerHTML = "";
    return;
  }
  searchTimer = setTimeout(async () => {
    try {
      const data = await api(`/api/search?q=${encodeURIComponent(q)}&limit=30`);
      const hits = data.rows || [];
      panel.innerHTML =
        `<div class="search-empty">共 ${data.total} 条，显示前 ${hits.length} 条</div>` +
        hits
          .map(
            (r) => `<div class="search-hit" data-bill="${esc(r.bill_id)}" data-cp="${esc(r.counterparty)}">
              <div class="top">
                <span>${esc(r.counterparty || "-")} · ${esc(r.category || "-")}</span>
                <span class="amt ${r.direction === "收入" ? "income" : "expense"}">${fmtMoney(r.amount)}</span>
              </div>
              <div class="sub">${esc(String(r.trade_time || "").slice(0, 16))} · ${esc(r.bill_id)} · ${esc(String(r.goods || "").slice(0, 18))}</div>
            </div>`
          )
          .join("");
      panel.classList.add("show");
      panel.querySelectorAll(".search-hit").forEach((el) =>
        el.addEventListener("click", async () => {
          panel.classList.remove("show");
          const billId = el.dataset.bill;
          if (billId && billId !== state.billId) await selectBill(billId);
          $("keyword").value = el.dataset.cp || "";
          applyFilter(() => {});
        })
      );
    } catch (e) {
      panel.innerHTML = `<div class="search-empty">${esc(e.message)}</div>`;
      panel.classList.add("show");
    }
  }, 300);
});

document.addEventListener("click", (e) => {
  if (!e.target.closest(".global-search")) $("searchPanel").classList.remove("show");
});

$("btnBackup").addEventListener("click", () => {
  window.open("/api/backup", "_blank");
});

$("restoreInput").addEventListener("change", async () => {
  const file = $("restoreInput").files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  showMsg("正在恢复备份...");
  try {
    const data = await api("/api/restore", { method: "POST", body: form });
    showMsg(`恢复完成，共还原 ${data.restored_files} 个文件`, "ok");
    await loadBillList();
    await refreshAll();
  } catch (e) {
    showMsg(e.message, "error");
  } finally {
    $("restoreInput").value = "";
  }
});

$("btnRebuildIndex").addEventListener("click", async () => {
  const el = $("indexMsg");
  el.className = "msg";
  el.textContent = "正在重建索引...";
  try {
    const data = await api("/api/store/rebuild", { method: "POST" });
    el.className = "msg ok";
    el.textContent = `索引完成：${data.bills} 个账单 / ${data.rows} 条交易`;
  } catch (e) {
    el.className = "msg error";
    el.textContent = e.message;
  }
});

$("yearSelect").addEventListener("change", async () => {
  state.year = $("yearSelect").value;
  if (!state.billId) return;
  try {
    const data = await api(
      `/api/bills/${state.billId}/year-report?year=${encodeURIComponent(state.year)}&${buildQuery()}`
    );
    renderYear(data);
  } catch (e) {
    showMsg(e.message, "error");
  }
});

/* ---------------- 筛选与导出 ---------------- */

$("btnApply").addEventListener("click", () => {
  state.page = 1;
  markQuickRange("");
  refreshAll().catch((e) => showMsg(e.message, "error"));
});

$("btnReset").addEventListener("click", () => {
  ["startDate", "endDate", "category", "keyword", "minAmount", "maxAmount", "weekday"].forEach(
    (id) => ($(id).value = "")
  );
  $("direction").value = "";
  $("excludeTransfer").checked = false;
  if ($("excludeIgnored")) $("excludeIgnored").checked = false;
  state.page = 1;
  markQuickRange("");
  refreshAll().catch((e) => showMsg(e.message, "error"));
});

function exportBill(fmt) {
  if (!state.billId) return showMsg("请先加载账单", "error");
  window.open(`/api/bills/${state.billId}/export?format=${fmt}&${buildQuery()}`, "_blank");
}

$("btnExportXlsx").addEventListener("click", () => exportBill("xlsx"));
$("btnExportCsv").addEventListener("click", () => exportBill("csv"));

/* ---------------- 图表 PNG 导出 ---------------- */

function bindChartDownloads() {
  document.querySelectorAll(".chart-box").forEach((box) => {
    const canvas = box.querySelector("canvas");
    const head = box.querySelector(".chart-head");
    if (!canvas || !head || head.querySelector(".chart-dl")) return;
    const btn = document.createElement("button");
    btn.className = "chart-dl";
    btn.textContent = "PNG";
    btn.addEventListener("click", () => {
      const url = canvas.toDataURL("image/png");
      const a = document.createElement("a");
      a.href = url;
      a.download = `${head.textContent.replace("PNG", "").trim() || "chart"}.png`;
      a.click();
    });
    head.appendChild(btn);
  });
}

/* ---------------- 初始化 ---------------- */

(async function init() {
  try {
    await api("/api/health");
    bindChartDownloads();
    await loadBillList();
  } catch (e) {
    showMsg("服务连接失败: " + e.message, "error");
  }
})();
