#include <QApplication>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLockFile>
#include <QMainWindow>
#include <QNetworkCookie>
#include <QProcess>
#include <QPushButton>
#include <QSaveFile>
#include <QTimer>
#include <QVBoxLayout>
#include <QWebEngineCookieStore>
#include <QWebEnginePage>
#include <QWebEngineProfile>
#include <QWebEngineView>
#include <sys/stat.h>
#include <unistd.h>

class PrivatePage : public QWebEnginePage {
public:
    using QWebEnginePage::QWebEnginePage;
protected:
    void javaScriptConsoleMessage(JavaScriptConsoleMessageLevel, const QString &, int, const QString &) override {}
    QWebEnginePage *createWindow(WebWindowType) override {
        auto owner = qobject_cast<QWidget *>(profile()->parent());
        auto popup = new QWebEngineView(owner);
        popup->setWindowFlag(Qt::Window);
        popup->setAttribute(Qt::WA_DeleteOnClose);
        popup->setWindowTitle("Pinterest · Авторизация");
        popup->resize(520, 760);
        auto page = new PrivatePage(profile(), popup);
        popup->setPage(page);
        popup->show();
        return page;
    }
};

int main(int argc, char **argv) {
    umask(0077);
    if (geteuid() == 0) qputenv("QTWEBENGINE_DISABLE_SANDBOX", "1");
    qputenv("QT_QUICK_BACKEND", "software");
    qputenv("QTWEBENGINE_CHROMIUM_FLAGS", qgetenv("QTWEBENGINE_CHROMIUM_FLAGS") + " --disable-gpu --disable-gpu-compositing --disable-dev-shm-usage");
    QApplication application(argc, argv);
    application.setApplicationName("Pinterest · Вход");
    QString root = QDir::homePath() + "/.local/state/pinterest-wallswap";
    QDir().mkpath(root);
    QFile::setPermissions(root, QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
    QLockFile lock(root + "/login.lock");
    if (!lock.tryLock(200)) return 0;
    qint64 started = QDateTime::currentSecsSinceEpoch();
    QMainWindow window;
    window.setWindowTitle("Pinterest · Вход");
    window.resize(520, 850);
    auto container = new QWidget(&window);
    auto layout = new QVBoxLayout(container);
    auto hint = new QLabel("Войдите на странице Pinterest. После входа окно закроется автоматически.", container);
    hint->setWordWrap(true);
    layout->addWidget(hint);
    auto address = new QLabel("https://www.pinterest.com", container);
    layout->addWidget(address);
    auto view = new QWebEngineView(container);
    // Off-the-record profile: passwords and browsing data are not stored on disk.
    auto profile = new QWebEngineProfile(&window);
    auto page = new PrivatePage(profile, view);
    view->setPage(page);
    layout->addWidget(view, 1);
    auto check = new QPushButton("Я вошёл — подключить аккаунт", container);
    check->setMinimumHeight(44);
    layout->addWidget(check);
    window.setCentralWidget(container);
    QList<QNetworkCookie> cookies;
    QProcess verifier;
    QTimer debounce;
    debounce.setSingleShot(true);
    debounce.setInterval(1800);
    auto exportSession = [&]() {
        if (verifier.state() != QProcess::NotRunning) return;
        bool authenticated = false;
        for (const auto &cookie : cookies)
            if (cookie.name() == "_auth" && cookie.value() == "1") authenticated = true;
        if (!authenticated) {
            hint->setText("Завершите вход на странице Pinterest, затем нажмите «Я вошёл».");
            return;
        }
        QSaveFile output(root + "/pinterest-cookies.txt");
        if (!output.open(QIODevice::WriteOnly)) { hint->setText("Не удалось сохранить сессию."); return; }
        output.setPermissions(QFile::ReadOwner | QFile::WriteOwner);
        output.write("# Netscape HTTP Cookie File\n");
        for (const auto &cookie : cookies) {
            QString domain = cookie.domain();
            bool include = domain.startsWith('.');
            if (cookie.isHttpOnly()) domain = "#HttpOnly_" + domain;
            QString path = cookie.path().isEmpty() ? "/" : cookie.path();
            QString expiry = cookie.isSessionCookie() ? "" : QString::number(cookie.expirationDate().toSecsSinceEpoch());
            output.write((domain + "\t" + (include ? "TRUE" : "FALSE") + "\t" + path + "\t" +
                         (cookie.isSecure() ? "TRUE" : "FALSE") + "\t" + expiry + "\t" +
                         QString::fromLatin1(cookie.name()) + "\t" + QString::fromLatin1(cookie.value()) + "\n").toUtf8());
        }
        if (!output.commit()) { hint->setText("Не удалось сохранить сессию."); return; }
        QSaveFile agent(root + "/user-agent.txt");
        if (agent.open(QIODevice::WriteOnly)) {
            agent.setPermissions(QFile::ReadOwner | QFile::WriteOwner);
            agent.write(profile->httpUserAgent().toUtf8());
            agent.commit();
        }
        hint->setText("Проверяю вход…");
        verifier.setStandardOutputFile(QProcess::nullDevice());
        verifier.setStandardErrorFile(QProcess::nullDevice());
        verifier.start("python", {QDir::homePath() + "/.config/omalauncher/widgets/pinterest-wallswap/account.py", "connect"});
    };
    QObject::connect(&debounce, &QTimer::timeout, &window, exportSession);
    QObject::connect(check, &QPushButton::clicked, &window, exportSession);
    QObject::connect(profile->cookieStore(), &QWebEngineCookieStore::cookieAdded, &window, [&](const QNetworkCookie &cookie) {
        QString host = cookie.domain();
        if (host.startsWith('.')) host.remove(0, 1);
        if (host != "pinterest.com" && !host.endsWith(".pinterest.com")) return;
        for (auto it = cookies.begin(); it != cookies.end();) {
            if (it->name() == cookie.name() && it->domain() == cookie.domain() && it->path() == cookie.path()) it = cookies.erase(it);
            else ++it;
        }
        cookies.append(cookie);
        debounce.start();
    });
    QObject::connect(profile->cookieStore(), &QWebEngineCookieStore::cookieRemoved, &window, [&](const QNetworkCookie &cookie) {
        for (auto it = cookies.begin(); it != cookies.end();) {
            if (it->name() == cookie.name() && it->domain() == cookie.domain() && it->path() == cookie.path()) it = cookies.erase(it);
            else ++it;
        }
    });
    QObject::connect(view, &QWebEngineView::urlChanged, &window, [&](const QUrl &url) {
        address->setText(url.scheme() + "://" + url.host());
    });
    QObject::connect(&verifier, &QProcess::finished, &window, [&](int, QProcess::ExitStatus) {
        QFile input(root + "/account.json");
        if (!input.open(QIODevice::ReadOnly)) return;
        auto data = QJsonDocument::fromJson(input.readAll()).object();
        if (data["connected"].toBool() && data["updated"].toDouble() >= started) application.closeAllWindows();
        else hint->setText(data["error"].toString("Не удалось подключить аккаунт. Завершите вход и попробуйте снова."));
    });
    if (application.arguments().contains("--self-test")) {
        QObject::connect(view, &QWebEngineView::loadFinished, &window, [&](bool ok) {
            if (!ok) { fprintf(stdout, "login-page-failed\n"); application.exit(2); return; }
            QTimer::singleShot(3000, &window, [&]() {
                page->runJavaScript("!!document.querySelector('input[type=email], input[type=password], input[name=id]')", [&](const QVariant &ready) {
                    window.grab().save(QDir::tempPath() + "/pinterest-login-preview.png");
                    fprintf(stdout, "%s\n", ready.toBool() ? "login-form-ready" : "login-page-loaded-form-not-detected");
                    application.exit(ready.toBool() ? 0 : 4);
                });
            });
        });
        QTimer::singleShot(40000, &application, [&]() { application.exit(3); });
    }
    view->load(QUrl("https://www.pinterest.com/login/"));
    window.show();
    return application.exec();
}
