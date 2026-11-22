#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// 极简静态文件服务：只监听 127.0.0.1 的随机端口，只处理 GET/HEAD。
@interface RCServer : NSObject

@property (nonatomic, readonly) NSInteger port;

- (BOOL)startWithSite:(NSString *)site error:(NSError **)error;
- (void)stop;

@end

NS_ASSUME_NONNULL_END
