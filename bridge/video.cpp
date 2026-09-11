// SovChat native shared-memory video item. Uses public Qt APIs only.
#include <QQuickPaintedItem>
#include <QQmlExtensionPlugin>
#include <QPainter>
#include <QTimer>
#include <QElapsedTimer>
#include <QRegularExpression>
#include <QtEndian>
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>
#include <cstring>

namespace {
constexpr size_t HeaderSize = 32;
constexpr size_t Capacity = HeaderSize + 2560 * 1440 * 4;
}

class VideoSurface : public QQuickPaintedItem {
    Q_OBJECT
    Q_PROPERTY(QString frameName READ frameName WRITE setFrameName NOTIFY frameNameChanged)
    Q_PROPERTY(bool hasFrame READ hasFrame NOTIFY frameChanged)
    Q_PROPERTY(int frameCount READ frameCount NOTIFY frameChanged)
public:
    explicit VideoSurface(QQuickItem *parent = nullptr) : QQuickPaintedItem(parent) {
        setAntialiasing(true);
        setOpaquePainting(true);
        timer.setInterval(33);
        connect(&timer, &QTimer::timeout, this, &VideoSurface::readFrame);
        connect(this, &QQuickItem::visibleChanged, this, [this] {
            if (isVisible()) timer.start(); else { timer.stop(); reset(); }
        });
        timer.start();
    }
    ~VideoSurface() override { reset(); }
    QString frameName() const { return name; }
    bool hasFrame() const { return !frame.isNull(); }
    int frameCount() const { return count; }
    void setFrameName(const QString &value) {
        if (name == value) return;
        reset();
        name = value;
        emit frameNameChanged();
    }
    void paint(QPainter *painter) override {
        painter->fillRect(boundingRect(), QColor("#111111"));
        if (frame.isNull()) return;
        const auto fitted = frame.size().scaled(boundingRect().size().toSize(), Qt::KeepAspectRatio);
        const QRectF target((width() - fitted.width()) / 2, (height() - fitted.height()) / 2,
                            fitted.width(), fitted.height());
        painter->setRenderHint(QPainter::SmoothPixmapTransform);
        painter->drawImage(target, frame);
    }
signals:
    void frameNameChanged();
    void frameChanged();
private:
    QString name;
    QTimer timer;
    QElapsedTimer fresh;
    QImage frame;
    int fd = -1;
    const uchar *memory = nullptr;
    quint64 sequence = 0;
    int count = 0;
    void reset() {
        if (memory) munmap(const_cast<uchar *>(memory), Capacity);
        if (fd >= 0) ::close(fd);
        fd = -1; memory = nullptr; sequence = 0; frame = QImage(); fresh.invalidate();
        emit frameChanged();
        update();
    }
    void readFrame() {
        if (!isVisible() || name.isEmpty()) return;
        if (fd < 0) {
            static const QRegularExpression allowed("^sovchat-frame-[0-9a-f]{32}$");
            if (!allowed.match(name).hasMatch()) return;
            const QByteArray path = ("/run/user/" + QString::number(getuid()) + "/" + name).toUtf8();
            fd = ::open(path.constData(), O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
            if (fd < 0) return;
            struct stat info{};
            if (fstat(fd, &info) || !S_ISREG(info.st_mode) || info.st_uid != getuid()
                || (info.st_mode & 077) || info.st_size != static_cast<off_t>(Capacity)) { reset(); return; }
            const void *mapped = mmap(nullptr, Capacity, PROT_READ, MAP_SHARED, fd, 0);
            if (mapped == MAP_FAILED) { reset(); return; }
            memory = static_cast<const uchar *>(mapped);
            fresh.start();
        }
        struct stat info{};
        if (fstat(fd, &info) || info.st_nlink == 0 || info.st_size != static_cast<off_t>(Capacity)) { reset(); return; }
        if (flock(fd, LOCK_SH | LOCK_NB)) return;
        const quint32 w = qFromLittleEndian<quint32>(memory + 8);
        const quint32 h = qFromLittleEndian<quint32>(memory + 12);
        const quint32 stride = qFromLittleEndian<quint32>(memory + 16);
        const quint32 bytes = qFromLittleEndian<quint32>(memory + 20);
        const quint64 next = qFromLittleEndian<quint64>(memory + 24);
        if (std::memcmp(memory, "SOVRGBA2", 8) || !w || !h || w > 2560 || h > 1440
            || stride != w * 4 || bytes != stride * h) {
            flock(fd, LOCK_UN); frame = QImage(); emit frameChanged(); update(); return;
        }
        if (next != sequence) {
            frame = QImage(memory + HeaderSize, w, h, stride, QImage::Format_RGBA8888).copy();
            sequence = next;
            ++count;
            fresh.restart();
            emit frameChanged();
            update();
        } else if (fresh.elapsed() > 1500 && !frame.isNull()) {
            frame = QImage(); emit frameChanged(); update(); // Never leave a crashed helper's private frame visible.
        }
        flock(fd, LOCK_UN);
    }
};

class SovchatVideoPlugin final : public QQmlExtensionPlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QQmlExtensionInterface_iid)
public:
    void registerTypes(const char *uri) override { qmlRegisterType<VideoSurface>(uri, 1, 0, "VideoSurface"); }
};

#include "video.moc"
