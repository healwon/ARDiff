public class fixedV {
    // reference fix: no express part, and free only from 100
    public static double snippet(int weight, int total, int express) {
        int base = 5;
        int extra = 0;
        int rush = 0;
        int fee = 0;
        if (weight > 10) {
            extra = weight / 2 - 5;
        }
        if (express == 1) {
            rush = 7;
        }
        fee = base + extra;
        if (total >= 100) {
            fee = 0;
        }
        return fee;
    }
}
