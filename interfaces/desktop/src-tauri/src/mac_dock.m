#import <AppKit/AppKit.h>

void set_macos_dock_icon_data(const unsigned char* data, unsigned long len) {
    if (!data || len == 0) {
        dispatch_async(dispatch_get_main_queue(), ^{
            [NSApp setApplicationIconImage:nil];
        });
        return;
    }
    NSData* nsData = [NSData dataWithBytes:data length:len];
    NSImage* image = [[NSImage alloc] initWithData:nsData];
    if (image) {
        dispatch_async(dispatch_get_main_queue(), ^{
            [NSApp setApplicationIconImage:image];
        });
    }
}
