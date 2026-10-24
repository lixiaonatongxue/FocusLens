/* FocusLens 本地报表前端（Vue3 + ECharts，资源全部本地化，无外部请求） */
"use strict";

const { createApp, computed, nextTick, onMounted, reactive } = Vue;

const state = reactive({
  tab: "today", // today | history
  historyView: "stack", // stack=逐日堆叠 | day=日期详情
  meta: { version: "", categories: {}, privacy: "default", focus_categories: [] },
  date: new Date().toLocaleDateString("sv-SE"), // 本地时区 YYYY-MM-DD
  historyDate: new Date(Date.now() - 86400000).toLocaleDateString("sv-SE"),
  summary: null,
  range: null,
  days: 14,
  loading: false,
  error: "",
});

const charts = {};

/* ---------- 工具 ---------- */

function catColor(cat) {
  const c = state.meta.categories[cat];
  return c ? c.color : "#A1A1AA";
}
function catName(cat) {
  const c = state.meta.categories[cat];
  return c ? c.name : cat;
}
function fmtDur(sec) {
  sec = Math.max(0, Math.round(sec));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h) return m ? `${h} 小时 ${m} 分` : `${h} 小时`;
  if (sec >= 60) return `${m} 分 ${sec % 60} 秒`;
  return `${sec} 秒`;
}
function fmtShort(sec) {
  sec = Math.max(0, Math.round(sec));
  if (sec < 60) return `${sec}s`;
  const h = Math.floor(sec / 3600);
  const m = Math.round((sec % 3600) / 60);
  return h ? `${h}h${String(m).padStart(2, "0")}m` : `${Math.floor(sec / 60)}m`;
}
function fmtClock(tsSec) {
  const d = new Date(tsSec * 1000);
  return (
    String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0")
  );
}

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`请求失败 HTTP ${r.status}`);
  return r.json();
}

/* ---------- 数据加载 ---------- */

async function loadMeta() {
  state.meta = await fetchJSON("/api/meta");
}

// 当前生效的日期：今日页用 state.date，历史-日期详情用 state.historyDate
const activeDate = computed({
  get: () => (state.tab === "today" ? state.date : state.historyDate),
  set: (v) => {
    if (state.tab === "today") state.date = v;
    else state.historyDate = v;
  },
});

async function loadSummary() {
  state.loading = true;
  state.error = "";
  try {
    state.summary = await fetchJSON(`/api/summary?date=${activeDate.value}`);
    await nextTick();
    renderToday();
  } catch (e) {
    state.error = String(e.message || e);
  }
  state.loading = false;
}

async function loadRange() {
  state.loading = true;
  state.error = "";
  try {
    state.range = await fetchJSON(`/api/range?days=${state.days}`);
    await nextTick();
    renderHistory();
  } catch (e) {
    state.error = String(e.message || e);
  }
  state.loading = false;
}

function switchTab(tab) {
  state.tab = tab;
  if (tab === "today") loadSummary();
  else if (state.historyView === "day") loadSummary();
  else loadRange();
}

function switchHistoryView(view) {
  if (state.historyView === view) return;
  state.historyView = view;
  if (view === "day") loadSummary();
  else loadRange();
}

/* ---------- 图表 ---------- */

function ensureChart(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  // Vue 用 v-if 切换标签页会销毁重建 DOM，旧图表实例仍绑在已移除的节点上，
  // 直接复用会画到"看不见"的画布——发现绑定节点变化时销毁重建。
  if (charts[id]) {
    if (charts[id].isDisposed() || charts[id].getDom() !== el) {
      charts[id].dispose();
      delete charts[id];
    }
  }
  if (!charts[id]) charts[id] = echarts.init(el);
  return charts[id];
}

function renderToday() {
  const s = state.summary;
  if (!s || !s.segment_count) return;

  // 24 小时时间线
  const tl = ensureChart("chart-timeline");
  if (tl) {
    const dayStart = new Date(s.date + "T00:00:00").getTime();
    tl.setOption(
      {
        animation: false,
        grid: { left: 46, right: 14, top: 16, bottom: 26 },
        tooltip: {
          formatter: (p) => {
            const [st, en, cat, app] = p.value;
            return `<b>${app}</b> · ${catName(cat)}<br>${fmtClock(st / 1000)} – ${fmtClock(
              en / 1000
            )} · ${fmtShort((en - st) / 1000)}`;
          },
        },
        xAxis: {
          type: "time",
          min: dayStart,
          max: dayStart + 86400000,
          axisLabel: {
            color: "#7E8798",
            formatter: (v) => {
              const h = new Date(v).getHours();
              return h % 3 === 0 ? String(h).padStart(2, "0") + ":00" : "";
            },
          },
          axisLine: { lineStyle: { color: "#2A3040" } },
          splitLine: { show: false },
        },
        yAxis: { show: false, min: 0, max: 1 },
        series: [
          {
            type: "custom",
            data: s.timeline.map((e) => ({
              value: [e.start * 1000, e.end * 1000, e.category, e.app],
              itemStyle: { color: catColor(e.category) },
            })),
            renderItem: (params, api) => {
              const start = api.coord([api.value(0), 0.5]);
              const end = api.coord([api.value(1), 0.5]);
              return {
                type: "rect",
                shape: {
                  x: start[0],
                  y: start[1] - 10,
                  width: Math.max(end[0] - start[0], 1.5),
                  height: 20,
                  r: 4,
                },
                style: api.style(),
              };
            },
          },
        ],
      },
      true
    );
  }

  // 类别占比环图
  const donut = ensureChart("chart-donut");
  if (donut) {
    donut.setOption(
      {
        animation: false,
        tooltip: {
          trigger: "item",
          formatter: (p) => `${p.marker} ${p.name} · ${fmtDur(p.value)}（${p.percent}%）`,
        },
        legend: {
          orient: "vertical",
          right: 6,
          top: "center",
          textStyle: { color: "#B7BFD1", fontSize: 12 },
          itemWidth: 10,
          itemHeight: 10,
          icon: "circle",
        },
        series: [
          {
            type: "pie",
            radius: ["58%", "80%"],
            center: ["34%", "50%"],
            label: { show: false },
            data: Object.entries(s.totals).map(([k, v]) => ({
              name: catName(k),
              value: v,
              itemStyle: { color: catColor(k) },
            })),
          },
        ],
        graphic: [
          {
            type: "text",
            left: "34%",
            top: "43%",
            style: {
              text: fmtShort(s.active_seconds),
              textAlign: "center",
              fill: "#EDF1F9",
              font: "600 20px 'Segoe UI', 'Microsoft YaHei', sans-serif",
            },
          },
          {
            type: "text",
            left: "34%",
            top: "56%",
            style: {
              text: "当日活跃",
              textAlign: "center",
              fill: "#7E8798",
              font: "12px 'Segoe UI', 'Microsoft YaHei', sans-serif",
            },
          },
        ],
      },
      true
    );
  }

  // Top 应用条形图
  const bar = ensureChart("chart-top");
  if (bar) {
    const apps = (s.top_apps || []).slice(0, 5);
    bar.setOption(
      {
        animation: false,
        grid: { left: 10, right: 70, top: 6, bottom: 6, containLabel: true },
        xAxis: { type: "value", show: false },
        yAxis: {
          type: "category",
          inverse: true,
          data: apps.map((a) => a.name),
          axisLabel: { color: "#C6CDDC" },
          axisLine: { show: false },
          axisTick: { show: false },
        },
        series: [
          {
            type: "bar",
            barWidth: 14,
            data: apps.map((a) => ({
              value: a.seconds,
              itemStyle: { color: catColor(a.category), borderRadius: 7 },
            })),
            label: { show: true, position: "right", color: "#8B93A6", formatter: (p) => fmtShort(p.value) },
            showBackground: true,
            backgroundStyle: { color: "rgba(148,163,184,0.08)", borderRadius: 7 },
          },
        ],
      },
      true
    );
  }
}

function renderHistory() {
  const r = state.range;
  if (!r || !r.days || !r.days.length) return;
  const hc = ensureChart("chart-history");
  if (!hc) return;
  const cats = Object.keys(state.meta.categories).filter((k) =>
    r.days.some((d) => (d.totals[k] || 0) > 0)
  );
  hc.setOption(
    {
      animation: false,
      grid: { left: 50, right: 16, top: 34, bottom: 26 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        valueFormatter: (v) => fmtDur(v || 0),
      },
      legend: {
        top: 0,
        textStyle: { color: "#B7BFD1", fontSize: 12 },
        itemWidth: 10,
        itemHeight: 10,
        icon: "circle",
      },
      xAxis: {
        type: "category",
        data: r.days.map((d) => d.date.slice(5)),
        axisLabel: { color: "#7E8798" },
        axisLine: { lineStyle: { color: "#2A3040" } },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: (value) => Math.max(3600, Math.ceil(value.max / 3600 / 2) * 2 * 3600),
        axisLabel: { color: "#7E8798", formatter: (v) => (v ? Math.round(v / 3600) + "h" : "0") },
        splitLine: { lineStyle: { color: "#222836" } },
      },
      series: cats.map((c) => ({
        name: catName(c),
        type: "bar",
        stack: "total",
        barWidth: 18,
        itemStyle: { color: catColor(c) },
        data: r.days.map((d) => d.totals[c] || 0),
      })),
    },
    true
  );
  // 点击柱子下钻到当天详情（off 防止重复注册）
  hc.off("click");
  hc.on("click", (params) => {
    if (!params || params.seriesType !== "bar") return;
    const d = state.range && state.range.days[params.dataIndex];
    if (!d) return;
    state.historyDate = d.date;
    state.historyView = "day";
    loadSummary();
  });
}

/* ---------- 视图 ---------- */

const emptyDay = computed(() => state.summary && !state.summary.segment_count);
const historyEmpty = computed(
  () =>
    state.range &&
    state.range.days &&
    state.range.days.every((d) => !d.active_seconds && !d.idle_seconds)
);
const topSessions = computed(() =>
  state.summary
    ? [...state.summary.focus.sessions].sort((a, b) => b.seconds - a.seconds).slice(0, 6)
    : []
);
const focusLabel = computed(() =>
  (state.meta.focus_categories || []).map(catName).join("/")
);

/* 单日详情卡片块：今日页与历史-日期详情共用（同一时刻只渲染其一） */
const DAY_DETAIL = `
    <div v-if="emptyDay" class="empty card">
      <p>这一天还没有记录。</p>
      <p class="hint">
        一次配置每天自动采集（推荐）：<code>python run.py autostart</code>；
        或先看演示数据：<code>python run.py demo</code>
      </p>
    </div>

    <div v-else-if="state.summary" class="cards">
      <div class="card span4 overview">
        <div class="big">{{ fmtDur(state.summary.active_seconds) }}</div>
        <div class="sub">当日活跃</div>
        <div class="row"><span>离开</span><b>{{ fmtDur(state.summary.idle_seconds) }}</b></div>
        <div class="row"><span>记录段数</span><b>{{ state.summary.segment_count }}</b></div>
        <div class="row"><span>专注合计</span><b>{{ fmtDur(state.summary.focus.total_seconds) }}</b></div>
      </div>
      <div class="card span4">
        <h3>类别占比</h3>
        <div id="chart-donut" class="chart h240"></div>
      </div>
      <div class="card span4">
        <h3>Top 应用</h3>
        <div id="chart-top" class="chart h240"></div>
      </div>
      <div class="card span12">
        <h3>24 小时时间线</h3>
        <div id="chart-timeline" class="chart h150"></div>
      </div>
      <div class="card span12">
        <h3>专注时段 <small>≥15 分钟的连续{{ focusLabel }}时间</small></h3>
        <div v-if="!topSessions.length" class="hint">这一天还没有 ≥15 分钟的专注段</div>
        <ul class="sessions">
          <li v-for="x in topSessions" :key="x.start">
            <span class="time">{{ fmtClock(x.start) }} – {{ fmtClock(x.end) }}</span>
            <b>{{ fmtDur(x.seconds) }}</b>
          </li>
        </ul>
      </div>
    </div>
`;

const template = `
<div class="wrap">
  <header class="topbar">
    <div class="brand">
      <span class="logo">◎</span>
      <div>
        <h1>FocusLens</h1>
        <p>焦点时间统计 · 数据 100% 留在本机</p>
      </div>
    </div>
    <nav class="tabs">
      <button :class="{on: state.tab==='today'}" @click="switchTab('today')">今日</button>
      <button :class="{on: state.tab==='history'}" @click="switchTab('history')">历史</button>
    </nav>
    <span class="badge">零上传 · v{{ state.meta.version }}</span>
  </header>

  <div v-if="state.error" class="error">{{ state.error }}</div>

  <!-- 今日 -->
  <template v-if="state.tab==='today'">
    <div class="toolbar">
      <input type="date" v-model="activeDate" @change="loadSummary">
      <span v-if="state.summary" class="weekday">{{ state.summary.date }} {{ state.summary.weekday }}</span>
    </div>
${DAY_DETAIL}
  </template>

  <!-- 历史 -->
  <template v-else>
    <div class="toolbar">
      <div class="seg">
        <button :class="{on: state.historyView==='stack'}" @click="switchHistoryView('stack')">逐日堆叠</button>
        <button :class="{on: state.historyView==='day'}" @click="switchHistoryView('day')">日期详情</button>
      </div>
      <select v-if="state.historyView==='stack'" v-model.number="state.days" @change="loadRange">
        <option :value="7">近 7 天</option>
        <option :value="14">近 14 天</option>
        <option :value="30">近 30 天</option>
      </select>
      <template v-if="state.historyView==='day'">
        <input type="date" v-model="activeDate" @change="loadSummary">
        <span v-if="state.summary" class="weekday">{{ state.summary.date }} {{ state.summary.weekday }}</span>
      </template>
    </div>

    <template v-if="state.historyView==='stack'">
      <div class="cards">
        <div class="card span12">
          <h3>逐日类别堆叠 <small>点击某天的柱子查看当天详情</small></h3>
          <div v-if="historyEmpty" class="hint">这段时间还没有任何记录</div>
          <div v-show="!historyEmpty" id="chart-history" class="chart h300"></div>
        </div>
      </div>
    </template>
    <template v-else>
${DAY_DETAIL}
    </template>
  </template>

  <footer>
    数据仅存于本机 SQLite（data/focuslens.db）· <code>python run.py clear --yes</code> 一键清除 ·
    本服务只监听 127.0.0.1
  </footer>
</div>`;

createApp({
  setup() {
    onMounted(async () => {
      window.addEventListener("resize", () =>
        Object.values(charts).forEach((c) => c.resize())
      );
      try {
        await loadMeta();
        await loadSummary();
      } catch (e) {
        state.error = String(e.message || e);
      }
    });
    return {
      state,
      activeDate,
      emptyDay,
      topSessions,
      focusLabel,
      switchTab,
      switchHistoryView,
      loadSummary,
      loadRange,
      fmtDur,
      fmtClock,
    };
  },
  template,
}).mount("#app");
