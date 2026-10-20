public class newV {
    // "simpler" start at 0: wrong when every value is negative
    public static double snippet(int a, int b, int c) {
        int largest = 0;
        if (b > largest) {
            largest = b;
        }
        if (c > largest) {
            largest = c;
        }
        return largest;
    }
}
