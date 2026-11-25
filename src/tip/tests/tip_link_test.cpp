// Windows only: the TIP's connection to the broker (BrokerLink in yuragi_tip.cpp, compiled in here).
#include "../yuragi_tip.cpp"

#include <cstdio>

int main() {
    // Switching input methods away and back in a window deactivates the TIP and activates it
    // again (Deactivate: link stopped; ActivateEx: started). If that happened while the link was
    // connecting or connected, the started link must still accept a connect request, or the TIP
    // never reaches the broker again and every key goes to the application untouched.
    // The thread may finish its attempt before the stop, so the case is repeated.
    for (int i = 0; i < 50; ++i) {
        BrokerLink link;
        link.Start(nullptr, 0);
        link.RequestConnect();
        link.Stop();
        link.Start(nullptr, 0);
        const bool idle = link.Idle();
        link.Stop();
        if (!idle) {
            std::fprintf(stderr, "FAIL: after deactivation and activation the link never connects again "
                                 "(case %d)\n", i);
            return 1;
        }
    }
    std::puts("tip_link: ok");
    return 0;
}
