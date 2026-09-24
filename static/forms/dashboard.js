(() => {
  const container = document.getElementById("response-trend");
  const data = document.getElementById("response-trend-data");
  if (!container || !data) return;
  const points = JSON.parse(data.textContent);
  if (!points.length) return;
  const ns = "http://www.w3.org/2000/svg";
  const node = (tag, attributes, text) => {
    const element = document.createElementNS(ns, tag);
    Object.entries(attributes || {}).forEach(([key, value]) => element.setAttribute(key, value));
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const svg = node("svg", { viewBox: "0 0 360 180", role: "group", "aria-label": "Tendencia de respuestas recibidas por día" });
  const max = Math.max(1, ...points.map((point) => point.count));
  const x = (index) => points.length === 1 ? 192 : 32 + index / (points.length - 1) * 318;
  const y = (count) => 144 - count / max * 128;
  [0, max].forEach((value) => {
    svg.append(node("line", { x1: 32, x2: 350, y1: y(value), y2: y(value), class: "chart-grid" }));
    svg.append(node("text", { x: 25, y: y(value) + 4, "text-anchor": "end" }, value));
  });
  svg.append(node("polyline", { points: points.map((point, index) => `${x(index)},${y(point.count)}`).join(" "), class: "chart-line" }));
  const readout = document.createElement("p");
  readout.className = "metrics-chart-readout";
  readout.setAttribute("aria-live", "polite");
  readout.textContent = "Pasa sobre un punto para ver sus respuestas.";
  points.forEach((point, index) => {
    const date = new Date(`${point.date}T12:00:00`);
    const label = `${date.toLocaleDateString("es-CO", { day: "numeric", month: "short" })}: ${point.count} respuestas`;
    const circle = node("circle", { cx: x(index), cy: y(point.count), r: points.length > 7 ? 3 : 4, tabindex: 0, role: "img", "aria-label": label });
    circle.append(node("title", {}, label));
    circle.addEventListener("mouseenter", () => { readout.textContent = label; });
    circle.addEventListener("focus", () => { readout.textContent = label; });
    svg.append(circle);
    if (points.length <= 7 || index === 0 || index === points.length - 1) {
      svg.append(node("text", { x: x(index), y: 172, "text-anchor": index === 0 ? "start" : index === points.length - 1 ? "end" : "middle" }, date.toLocaleDateString("es-CO", points.length <= 7 ? { weekday: "short" } : { day: "numeric", month: "short" })));
    }
  });
  container.append(svg, readout);
})();
