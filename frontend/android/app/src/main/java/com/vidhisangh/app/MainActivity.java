package com.vidhisangh.app;

import android.os.Bundle;
import androidx.activity.EdgeToEdge;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // Draw edge-to-edge on every Android version, not only 15+ (Play
        // requirement). Capacitor's SystemBars pads the WebView clear of the
        // status and navigation bars, so content never sits under them.
        registerPlugin(InAppReviewPlugin.class);  // the app's own plugin: before super
        super.onCreate(savedInstanceState);
        EdgeToEdge.enable(this);
    }
}
