public class oldV {
    // readable: start from the first value
    public static double snippet(int a, int b, int c) {
        int largest = a;
        if (b > largest) {
            largest = b;
        }
        if (c > largest) {
            largest = c;
        }
        return largest;
    }
}
