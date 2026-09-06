/* receipt-window - macOS event-receipt test fixture for computer-automation.
 *
 * Listens (listen-only, non-invasive) for mouse and keyboard events on the
 * session tap and prints one JSON line per event with a monotonic timestamp:
 *   {"type":"keyDown","ts_ns":123456789,"keycode":36}
 *   {"type":"leftMouseDown","ts_ns":...,"x":640,"y":420}
 *
 * Used to measure effect_ns (event receipt) versus dispatch_ns (helper exit)
 * for the benchmark suite. Requires Accessibility trust like cghelper.
 * Prints events to stdout; never posts or modifies events (listen-only).
 *
 * Build: clang -O2 -o build/receipt-window native/receipt-window.c \
 *          -framework CoreGraphics -framework ApplicationServices
 * Usage: build/receipt-window <seconds>   (default 5)
 */

#include <ApplicationServices/ApplicationServices.h>
#include <CoreGraphics/CoreGraphics.h>
#include <mach/mach_time.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static mach_timebase_info_data_t tb;

static double now_ns(void) {
  uint64_t t = mach_absolute_time();
  return (double)t * tb.numer / tb.denom;
}

static const char *type_name(CGEventType t) {
  switch (t) {
  case kCGEventLeftMouseDown: return "leftMouseDown";
  case kCGEventLeftMouseUp: return "leftMouseUp";
  case kCGEventRightMouseDown: return "rightMouseDown";
  case kCGEventRightMouseUp: return "rightMouseUp";
  case kCGEventOtherMouseDown: return "otherMouseDown";
  case kCGEventOtherMouseUp: return "otherMouseUp";
  case kCGEventMouseMoved: return "mouseMoved";
  case kCGEventLeftMouseDragged: return "leftMouseDragged";
  case kCGEventKeyDown: return "keyDown";
  case kCGEventKeyUp: return "keyUp";
  case kCGEventFlagsChanged: return "flagsChanged";
  case kCGEventScrollWheel: return "scrollWheel";
  default: return "other";
  }
}

static CGEventRef callback(CGEventTapProxy proxy, CGEventType type,
                           CGEventRef event, void *refcon) {
  (void)proxy;
  if (type == kCGEventTapDisabledByTimeout ||
      type == kCGEventTapDisabledByUserInput) {
    CGEventTapEnable((CFMachPortRef)refcon, true);
    return event;
  }
  double ts = now_ns();
  CGPoint loc = CGEventGetLocation(event);
  long long extra = 0;
  if (type == kCGEventKeyDown || type == kCGEventKeyUp ||
      type == kCGEventFlagsChanged)
    extra = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode);
  printf("{\"type\":\"%s\",\"ts_ns\":%.0f,\"x\":%.0f,\"y\":%.0f,\"keycode\":%lld}\n",
         type_name(type), ts, loc.x, loc.y, extra);
  fflush(stdout);
  return event;
}

int main(int argc, char **argv) {
  mach_timebase_info(&tb);
  double duration = argc > 1 ? atof(argv[1]) : 5.0;
  if (duration <= 0 || duration > 600) {
    fprintf(stderr, "usage: receipt-window <seconds 0-600>\n");
    return 2;
  }

  CGEventMask mask = CGEventMaskBit(kCGEventKeyDown) |
                     CGEventMaskBit(kCGEventKeyUp) |
                     CGEventMaskBit(kCGEventFlagsChanged) |
                     CGEventMaskBit(kCGEventLeftMouseDown) |
                     CGEventMaskBit(kCGEventLeftMouseUp) |
                     CGEventMaskBit(kCGEventRightMouseDown) |
                     CGEventMaskBit(kCGEventRightMouseUp) |
                     CGEventMaskBit(kCGEventScrollWheel);

  CFMachPortRef tap = CGEventTapCreate(
      kCGSessionEventTap, kCGTailAppendEventTap,
      kCGEventTapOptionListenOnly, mask, callback, NULL);
  if (tap == NULL) {
    fprintf(stderr, "receipt-window: CGEventTapCreate failed "
                    "(needs Accessibility trust)\n");
    return 3;
  }
  CFRunLoopSourceRef src = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0);
  CFRunLoopAddSource(CFRunLoopGetCurrent(), src, kCFRunLoopCommonModes);
  CGEventTapEnable(tap, true);

  CFRunLoopRunInMode(kCFRunLoopDefaultMode, duration, false);
  CFRelease(tap);
  CFRelease(src);
  return 0;
}
