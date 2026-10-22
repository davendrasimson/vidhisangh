package com.vidhisangh.app;

import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.google.android.play.core.review.ReviewInfo;
import com.google.android.play.core.review.ReviewManager;
import com.google.android.play.core.review.ReviewManagerFactory;

/**
 * Google Play's in-app rating sheet (core/platform/review-prompt.ts decides
 * when to ask). Play decides whether the sheet actually appears and never says
 * whether the person rated, so this resolves either way once the flow ends.
 */
@CapacitorPlugin(name = "InAppReview")
public class InAppReviewPlugin extends Plugin {
    @PluginMethod
    public void requestReview(PluginCall call) {
        ReviewManager manager = ReviewManagerFactory.create(getContext());
        manager.requestReviewFlow().addOnCompleteListener(request -> {
            if (!request.isSuccessful()) {
                call.reject("Rating is not available right now.");
                return;
            }
            ReviewInfo info = request.getResult();
            manager.launchReviewFlow(getActivity(), info).addOnCompleteListener(flow -> call.resolve());
        });
    }
}
