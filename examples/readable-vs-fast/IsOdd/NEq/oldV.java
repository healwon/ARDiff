public class oldV {
    // readable: odd means a non-zero remainder
    public static double snippet(int x) {
        int odd = 0;
        if (x % 2 != 0) {
            odd = 1;
        }
        return odd;
    }
}
