import QtQuick
import QtQuick.Shapes

Item {
  id: root
  property string kind: "voice"
  property color color: "#e8e8e8"
  implicitWidth: 20
  implicitHeight: 20
  readonly property int rendererType: shape.rendererType
  // Original native-Linux icon paths, ported from components/linux-glyph.tsx.
  readonly property var paths: ({
    mail: "M2 4H18V16H2Z M2 4L10 11L18 4",
    lock: "M4 9H16V18H4Z M6 9V6A4 4 0 0 1 14 6V9 M10 12V15",
    chat: "M2.5 3.5h15v10h-8l-4.5 3v-3H2.5z M6 7.5h8M6 10h5",
    microphone: "M7 2.5h6v9H7z M4.5 9v2.5c0 2.2 2.4 4 5.5 4s5.5-1.8 5.5-4V9M10 15.5v2M7 17.5h6",
    headphones: "M3 10V8.5C3 4.9 5.8 2 10 2s7 2.9 7 6.5V10 M3 9.5h3v7H3zM14 9.5h3v7h-3z",
    noise: "M2.5 10h3l1.5-5 2.2 10 2.1-8 1.4 5h4.8 M2.5 4v3M2.5 13v3M17.5 4v3M17.5 13v3",
    settings: "M2.5 5h15M2.5 10h15M2.5 15h15 M6 3v4M13.5 8v4M8.5 13v4",
    share: "M2.5 4.5h9v8h-9zM5 15.5h7M8.5 12.5v3 M11 8.5 17 2.5M13 2.5h4v4",
    voice: "M3 13V7M7.5 16V4M12.5 14V6M17 12V8",
    close: "M4 4L16 16 M16 4L4 16",
    send: "M3 3L18 10L3 17L6 10Z M6 10H18",
    attach: "M7 11L13 5C17 1 21 5 17 9L9 17C3 23-3 17 3 11L11 3 M6 13L13 6",
    smile: "M18 10A8 8 0 1 1 2 10A8 8 0 1 1 18 10 M6 12Q10 17 14 12 M6 7H7 M13 7H14",
    palette: "M18 9C18 3 12 1 7 3C1 5 0 12 5 16C9 20 13 17 11 14C10 12 13 11 16 12Q19 12 18 9 M6 7H7M10 5H11M14 7H15M4 11H5",
    monitor: "M2 3H18V14H2Z M10 14V18 M6 18H14",
    people: "M7 3A3 3 0 1 0 7 9A3 3 0 1 0 7 3 M1 18V15Q1 11 7 11Q13 11 13 15V18 M14 3Q20 6 14 9 M15 11Q19 12 19 17",
    wrench: "M12 3L11 7L14 10L18 9Q19 15 13 14L6 19L2 15L8 9Q6 3 12 3Z"
  })
  Shape {
    id: shape
    // GeometryRenderer depends on host MSAA, which the VM shell does not enable.
    // CurveRenderer antialiases paths analytically, including fractional scales.
    preferredRendererType: Shape.CurveRenderer
    antialiasing: true
    width: 20; height: 20
    transform: Scale { xScale: root.width / 20; yScale: root.height / 20 }
    ShapePath {
      fillColor: "transparent"; strokeColor: root.color
      strokeWidth: root.kind === "voice" ? 2.2 : 1.5
      capStyle: ShapePath.SquareCap; joinStyle: ShapePath.MiterJoin
      PathSvg { path: root.paths[root.kind] || root.paths.voice }
    }
  }
}
