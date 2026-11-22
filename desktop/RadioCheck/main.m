#import <Cocoa/Cocoa.h>
#import <WebKit/WebKit.h>

#import "RCServer.h"

@interface AppDelegate : NSObject <NSApplicationDelegate, WKNavigationDelegate>
@property (strong) NSWindow *window;
@property (strong) WKWebView *webView;
@property (strong) RCServer *server;
@end

@implementation AppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [self buildMenu];
    [self buildWindow];
    [self startAndLoad];
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender {
    return YES;
}

- (void)applicationWillTerminate:(NSNotification *)notification {
    [self.server stop];
}

- (void)buildWindow {
    WKWebViewConfiguration *config = [[WKWebViewConfiguration alloc] init];
    config.websiteDataStore = [WKWebsiteDataStore defaultDataStore];
    self.webView = [[WKWebView alloc] initWithFrame:NSZeroRect configuration:config];
    self.webView.navigationDelegate = self;
    self.webView.allowsBackForwardNavigationGestures = YES;

    NSRect rect = NSMakeRect(0, 0, 1440, 950);
    NSWindowStyleMask style = NSWindowStyleMaskTitled |
                              NSWindowStyleMaskClosable |
                              NSWindowStyleMaskMiniaturizable |
                              NSWindowStyleMaskResizable;
    self.window = [[NSWindow alloc] initWithContentRect:rect
                                              styleMask:style
                                                backing:NSBackingStoreBuffered
                                                  defer:NO];
    self.window.title = @"RadioCheck · 胸片阅片";
    self.window.minSize = NSMakeSize(1100, 720);
    [self.window center];
    self.window.contentView = self.webView;
    [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];
}

- (void)startAndLoad {
    NSURL *resources = [[NSBundle mainBundle] resourceURL];
    if (!resources) {
        [self showError:@"找不到应用资源目录。"];
        return;
    }
    NSString *site = [[resources URLByAppendingPathComponent:@"site" isDirectory:YES] path];
    if (![[NSFileManager defaultManager] fileExistsAtPath:site]) {
        [self showError:@"应用内没有站点文件，请重新构建。"];
        return;
    }

    RCServer *server = [[RCServer alloc] init];
    NSError *error = nil;
    if (![server startWithSite:site error:&error]) {
        [self showError:[NSString stringWithFormat:@"本地服务启动失败：%@", error.localizedDescription]];
        return;
    }
    self.server = server;

    NSURL *url = [NSURL URLWithString:[NSString stringWithFormat:@"http://127.0.0.1:%ld/", (long)server.port]];
    [self.webView loadRequest:[NSURLRequest requestWithURL:url]];
}

- (void)showError:(NSString *)message {
    NSString *html = [NSString stringWithFormat:
        @"<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\">"
         "<body style=\"margin:0;background:#f4fbfa;color:#10232e;"
         "font:15px/1.8 -apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;"
         "display:grid;place-items:center;height:100vh\">"
         "<div style=\"max-width:560px;padding:28px;background:#fff;border:1px solid #dcebe8;border-radius:16px\">"
         "<h1 style=\"font-size:20px;margin:0 0 8px\">桌面入口启动失败</h1>"
         "<p style=\"color:#5b7480;margin:0 0 14px\">%@</p>"
         "<p style=\"color:#5b7480;margin:0\">兜底方式：双击项目里的 <code>desktop/start.command</code>，"
         "或运行 <code>cd outputs/medtrain &amp;&amp; python3 -m http.server 8080</code>。</p>"
         "</div></body></html>", message];
    [self.webView loadHTMLString:html baseURL:nil];
}

#pragma mark - Navigation

- (void)webView:(WKWebView *)webView
    decidePolicyForNavigationAction:(WKNavigationAction *)navigationAction
    decisionHandler:(void (^)(WKNavigationActionPolicy))decisionHandler {
    NSURL *url = navigationAction.request.URL;
    NSString *scheme = url.scheme.lowercaseString;
    if ([scheme isEqualToString:@"http"] || [scheme isEqualToString:@"https"]) {
        if ([url.host isEqualToString:@"127.0.0.1"] || [url.host isEqualToString:@"localhost"]) {
            decisionHandler(WKNavigationActionPolicyAllow);
        } else {
            [[NSWorkspace sharedWorkspace] openURL:url];
            decisionHandler(WKNavigationActionPolicyCancel);
        }
        return;
    }
    if ([scheme isEqualToString:@"file"]) {
        decisionHandler(WKNavigationActionPolicyAllow);
        return;
    }
    [[NSWorkspace sharedWorkspace] openURL:url];
    decisionHandler(WKNavigationActionPolicyCancel);
}

#pragma mark - Menu

- (void)buildMenu {
    NSMenu *mainMenu = [[NSMenu alloc] init];

    NSMenuItem *appItem = [[NSMenuItem alloc] init];
    [mainMenu addItem:appItem];
    NSMenu *appMenu = [[NSMenu alloc] init];
    [appMenu addItemWithTitle:@"关于 RadioCheck"
                       action:@selector(orderFrontStandardAboutPanel:)
                keyEquivalent:@""];
    [appMenu addItem:[NSMenuItem separatorItem]];
    [appMenu addItemWithTitle:@"隐藏 RadioCheck"
                       action:@selector(hide:)
                keyEquivalent:@"h"];
    NSMenuItem *hideOthers = [appMenu addItemWithTitle:@"隐藏其他"
                                                action:@selector(hideOtherApplications:)
                                         keyEquivalent:@"h"];
    hideOthers.keyEquivalentModifierMask = NSEventModifierFlagCommand | NSEventModifierFlagOption;
    [appMenu addItem:[NSMenuItem separatorItem]];
    [appMenu addItemWithTitle:@"退出 RadioCheck"
                       action:@selector(terminate:)
                keyEquivalent:@"q"];
    appItem.submenu = appMenu;

    NSMenuItem *viewItem = [[NSMenuItem alloc] init];
    [mainMenu addItem:viewItem];
    NSMenu *viewMenu = [[NSMenu alloc] initWithTitle:@"显示"];
    NSMenuItem *reload = [[NSMenuItem alloc] initWithTitle:@"重新载入"
                                                   action:@selector(reloadPage)
                                            keyEquivalent:@"r"];
    reload.target = self;
    [viewMenu addItem:reload];
    NSMenuItem *actual = [[NSMenuItem alloc] initWithTitle:@"实际大小"
                                                   action:@selector(actualSize)
                                            keyEquivalent:@"0"];
    actual.target = self;
    [viewMenu addItem:actual];
    NSMenuItem *zoomIn = [[NSMenuItem alloc] initWithTitle:@"放大"
                                                   action:@selector(zoomIn)
                                            keyEquivalent:@"+"];
    zoomIn.target = self;
    [viewMenu addItem:zoomIn];
    NSMenuItem *zoomOut = [[NSMenuItem alloc] initWithTitle:@"缩小"
                                                    action:@selector(zoomOut)
                                             keyEquivalent:@"-"];
    zoomOut.target = self;
    [viewMenu addItem:zoomOut];
    [viewMenu addItem:[NSMenuItem separatorItem]];
    NSMenuItem *fullScreen = [[NSMenuItem alloc] initWithTitle:@"进入全屏"
                                                       action:@selector(toggleFullScreen:)
                                                keyEquivalent:@"f"];
    fullScreen.keyEquivalentModifierMask = NSEventModifierFlagCommand | NSEventModifierFlagControl;
    [viewMenu addItem:fullScreen];
    viewItem.submenu = viewMenu;

    NSMenuItem *windowItem = [[NSMenuItem alloc] init];
    [mainMenu addItem:windowItem];
    NSMenu *windowMenu = [[NSMenu alloc] initWithTitle:@"窗口"];
    [windowMenu addItemWithTitle:@"最小化"
                          action:@selector(miniaturize:)
                   keyEquivalent:@"m"];
    [windowMenu addItemWithTitle:@"缩放"
                          action:@selector(zoom:)
                   keyEquivalent:@""];
    windowItem.submenu = windowMenu;

    NSApp.mainMenu = mainMenu;
    NSApp.windowsMenu = windowMenu;
}

- (void)reloadPage {
    [self.webView reload];
}

- (void)actualSize {
    self.webView.pageZoom = 1.0;
}

- (void)zoomIn {
    self.webView.pageZoom = MIN(self.webView.pageZoom + 0.1, 2.0);
}

- (void)zoomOut {
    self.webView.pageZoom = MAX(self.webView.pageZoom - 0.1, 0.6);
}

@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSApplication *app = [NSApplication sharedApplication];
        AppDelegate *delegate = [[AppDelegate alloc] init];
        app.delegate = delegate;
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        [app run];
    }
    return 0;
}
