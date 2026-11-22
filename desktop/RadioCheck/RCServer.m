#import "RCServer.h"

#import <arpa/inet.h>
#import <errno.h>
#import <netinet/in.h>
#import <sys/socket.h>
#import <unistd.h>

@interface RCServer ()
@property (nonatomic, copy) NSString *site;
@property (nonatomic, assign) int listenFD;
@property (nonatomic, assign) NSInteger port;
@property (nonatomic, assign) BOOL running;
@end

@implementation RCServer

- (instancetype)init {
    self = [super init];
    if (self) {
        _listenFD = -1;
        _port = 0;
        _running = NO;
    }
    return self;
}

- (BOOL)startWithSite:(NSString *)site error:(NSError **)error {
    self.site = [site stringByStandardizingPath];

    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) {
        [self fail:error message:@"无法创建本地服务 socket。"];
        return NO;
    }

    int yes = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = 0;
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);

    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(fd);
        [self fail:error message:@"无法绑定 127.0.0.1。"];
        return NO;
    }
    if (listen(fd, 64) < 0) {
        close(fd);
        [self fail:error message:@"本地服务无法监听。"];
        return NO;
    }

    socklen_t len = sizeof(addr);
    if (getsockname(fd, (struct sockaddr *)&addr, &len) < 0) {
        close(fd);
        [self fail:error message:@"无法读取本地服务端口。"];
        return NO;
    }

    self.listenFD = fd;
    self.port = ntohs(addr.sin_port);
    self.running = YES;

    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        [self acceptLoop];
    });
    return YES;
}

- (void)stop {
    self.running = NO;
    if (self.listenFD >= 0) {
        close(self.listenFD);
        self.listenFD = -1;
    }
}

- (void)fail:(NSError **)error message:(NSString *)message {
    if (error) {
        *error = [NSError errorWithDomain:@"RCServer"
                                     code:1
                                 userInfo:@{NSLocalizedDescriptionKey: message}];
    }
}

- (void)acceptLoop {
    while (self.running) {
        int client = accept(self.listenFD, NULL, NULL);
        if (client < 0) {
            if (errno == EINTR) {
                continue;
            }
            break;
        }
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
            [self handleClient:client];
        });
    }
}

- (void)handleClient:(int)client {
    @autoreleasepool {
        struct timeval timeout = {5, 0};
        setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));

        NSMutableData *request = [NSMutableData data];
        char buffer[4096];
        NSData *marker = [@"\r\n\r\n" dataUsingEncoding:NSASCIIStringEncoding];
        while (request.length < 65536) {
            ssize_t n = recv(client, buffer, sizeof(buffer), 0);
            if (n <= 0) {
                break;
            }
            [request appendBytes:buffer length:(NSUInteger)n];
            if ([request rangeOfData:marker options:0 range:NSMakeRange(0, request.length)].location != NSNotFound) {
                break;
            }
        }

        NSString *head = [[NSString alloc] initWithData:request encoding:NSUTF8StringEncoding];
        if (head.length == 0) {
            close(client);
            return;
        }

        NSString *firstLine = [[head componentsSeparatedByString:@"\r\n"] firstObject] ?: @"";
        NSArray<NSString *> *parts = [firstLine componentsSeparatedByString:@" "];
        if (parts.count < 2) {
            [self sendStatus:400 client:client];
            close(client);
            return;
        }

        NSString *method = parts[0];
        if (!([method isEqualToString:@"GET"] || [method isEqualToString:@"HEAD"])) {
            [self sendStatus:405 client:client];
            close(client);
            return;
        }

        NSString *path = parts[1];
        NSRange query = [path rangeOfString:@"?"];
        if (query.location != NSNotFound) {
            path = [path substringToIndex:query.location];
        }
        path = [path stringByRemovingPercentEncoding] ?: path;
        if ([path isEqualToString:@"/"] || path.length == 0) {
            path = @"/index.html";
        }

        NSString *relative = [path hasPrefix:@"/"] ? [path substringFromIndex:1] : path;
        NSString *full = [[self.site stringByAppendingPathComponent:relative] stringByStandardizingPath];
        NSString *prefix = [self.site stringByAppendingString:@"/"];
        if (![full isEqualToString:self.site] && ![full hasPrefix:prefix]) {
            [self sendStatus:403 client:client];
            close(client);
            return;
        }

        NSFileManager *fm = [NSFileManager defaultManager];
        BOOL isDir = NO;
        if ([fm fileExistsAtPath:full isDirectory:&isDir] && isDir) {
            full = [full stringByAppendingPathComponent:@"index.html"];
        }
        if (![fm fileExistsAtPath:full]) {
            [self sendStatus:404 client:client];
            close(client);
            return;
        }

        NSData *data = [NSData dataWithContentsOfFile:full];
        if (!data) {
            [self sendStatus:500 client:client];
            close(client);
            return;
        }

        NSString *header = [NSString stringWithFormat:
            @"HTTP/1.1 200 OK\r\n"
             "Content-Type: %@\r\n"
             "Content-Length: %lu\r\n"
             "Cache-Control: no-store, max-age=0\r\n"
             "Connection: close\r\n\r\n",
            [self mimeForPath:full], (unsigned long)data.length];

        [self sendData:[header dataUsingEncoding:NSUTF8StringEncoding] client:client];
        if (![method isEqualToString:@"HEAD"]) {
            [self sendData:data client:client];
        }
        close(client);
    }
}

- (void)sendStatus:(int)code client:(int)client {
    NSString *text = @"Error";
    if (code == 400) text = @"Bad Request";
    if (code == 403) text = @"Forbidden";
    if (code == 404) text = @"Not Found";
    if (code == 405) text = @"Method Not Allowed";
    if (code == 500) text = @"Internal Server Error";

    NSString *body = [NSString stringWithFormat:@"<h1>%d %@</h1>", code, text];
    NSData *data = [body dataUsingEncoding:NSUTF8StringEncoding];
    NSString *header = [NSString stringWithFormat:
        @"HTTP/1.1 %d %@\r\n"
         "Content-Type: text/html; charset=utf-8\r\n"
         "Content-Length: %lu\r\n"
         "Connection: close\r\n\r\n",
        code, text, (unsigned long)data.length];
    [self sendData:[header dataUsingEncoding:NSUTF8StringEncoding] client:client];
    [self sendData:data client:client];
}

- (void)sendData:(NSData *)data client:(int)client {
    const uint8_t *bytes = data.bytes;
    NSUInteger remaining = data.length;
    while (remaining > 0) {
        ssize_t n = send(client, bytes, remaining, 0);
        if (n <= 0) {
            if (errno == EINTR) {
                continue;
            }
            break;
        }
        bytes += n;
        remaining -= (NSUInteger)n;
    }
}

- (NSString *)mimeForPath:(NSString *)path {
    NSString *ext = path.pathExtension.lowercaseString;
    if ([ext isEqualToString:@"html"]) return @"text/html; charset=utf-8";
    if ([ext isEqualToString:@"css"]) return @"text/css; charset=utf-8";
    if ([ext isEqualToString:@"js"]) return @"text/javascript; charset=utf-8";
    if ([ext isEqualToString:@"json"]) return @"application/json; charset=utf-8";
    if ([ext isEqualToString:@"webmanifest"]) return @"application/manifest+json";
    if ([ext isEqualToString:@"svg"]) return @"image/svg+xml";
    if ([ext isEqualToString:@"png"]) return @"image/png";
    if ([ext isEqualToString:@"jpg"] || [ext isEqualToString:@"jpeg"]) return @"image/jpeg";
    if ([ext isEqualToString:@"md"]) return @"text/markdown; charset=utf-8";
    return @"application/octet-stream";
}

@end
