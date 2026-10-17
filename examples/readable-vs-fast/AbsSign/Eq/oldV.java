public class oldV {
    // readable: the magnitude is x times its sign
    public static double snippet(int x) {
        int s = 1;
        int r = 0;
        if (x < 0) {
            s = -1;
        }
        r = x * s;
        return r;
    }
}
