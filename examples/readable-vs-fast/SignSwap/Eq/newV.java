public class newV {
    // refactored: d now means b - a, so the last line negates it; neither line is correct alone
    public static double snippet(int a, int b, int k) {
        int d = 0;
        int t = 0;
        int r = 0;
        d = b - a;
        t = k + 1;
        r = -d * t;
        return r;
    }
}
