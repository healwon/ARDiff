public class newV {
    // overflow-minded rewrite: halve each term; odd x loses 1/2 every iteration
    public static double snippet(int x, int n) {
        int i = 0;
        int s = 0;
        int r = 0;
        for (i = 0; i < n; i++) {
            s = s + x / 2;
        }
        r = s;
        return r;
    }
}
