public class oldV {
    // readable: distance a - b, scaled by k + 1
    public static double snippet(int a, int b, int k) {
        int d = 0;
        int t = 0;
        int r = 0;
        d = a - b;
        t = k + 1;
        r = d * t;
        return r;
    }
}
