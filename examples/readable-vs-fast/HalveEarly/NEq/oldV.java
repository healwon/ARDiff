public class oldV {
    // readable: add everything, halve once at the end
    public static double snippet(int x, int n) {
        int i = 0;
        int s = 0;
        int r = 0;
        for (i = 0; i < n; i++) {
            s = s + x;
        }
        r = s / 2;
        return r;
    }
}
